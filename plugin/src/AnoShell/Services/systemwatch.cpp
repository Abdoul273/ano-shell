#include "systemwatch.hpp"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <dirent.h>
#include <qdir.h>
#include <qfile.h>
#include <qfileinfo.h>
#include <unistd.h>

namespace anoshell::services {

namespace {

[[nodiscard]] QString readTrimmed(const QString& path) {
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly | QIODevice::Text)) {
        return {};
    }
    return QString::fromUtf8(file.readAll()).trimmed();
}

[[nodiscard]] qint64 readInt64(const QString& path, bool* ok = nullptr) {
    const QString text = readTrimmed(path);
    if (text.isEmpty()) {
        if (ok) {
            *ok = false;
        }
        return 0;
    }
    return text.toLongLong(ok);
}

[[nodiscard]] bool isAllDigits(const char* name) {
    if (!name || *name == '\0') {
        return false;
    }
    for (const char* p = name; *p != '\0'; ++p) {
        if (*p < '0' || *p > '9') {
            return false;
        }
    }
    return true;
}

} // namespace

SystemWatch::SystemWatch(QObject* parent)
    : TickingService(parent) {
    discoverPathsOnce();
    pollBattery();
    pollCapsLock();
}

bool SystemWatch::batteryPresent() const {
    return m_batteryPresent;
}

int SystemWatch::batteryPercentage() const {
    return m_batteryPercentage;
}

QString SystemWatch::batteryStatus() const {
    return m_batteryStatus;
}

bool SystemWatch::batteryCharging() const {
    return m_batteryCharging;
}

qreal SystemWatch::batteryWatts() const {
    return m_batteryWatts;
}

bool SystemWatch::onAcPower() const {
    return m_onAcPower;
}

bool SystemWatch::capsLock() const {
    return m_capsLock;
}

bool SystemWatch::cameraActive() const {
    return m_cameraActive;
}

void SystemWatch::refreshNow() {
    discoverPathsOnce();
    pollBattery();
    pollCapsLock();
    pollCamera();
}

void SystemWatch::discoverPathsOnce() {
    if (m_discovered) {
        return;
    }
    m_discovered = true;

    const QDir psDir(QStringLiteral("/sys/class/power_supply"));
    for (const QString& entry : psDir.entryList(QDir::Dirs | QDir::NoDotAndDotDot)) {
        const QString full = psDir.filePath(entry);
        const QString type = readTrimmed(full + QStringLiteral("/type"));
        if (m_batteryDir.isEmpty() && type == QStringLiteral("Battery")) {
            m_batteryDir = full;
        } else if (m_acDir.isEmpty() && type == QStringLiteral("Mains")) {
            m_acDir = full;
        }
    }

    const QDir ledsDir(QStringLiteral("/sys/class/leds"));
    for (const QString& entry : ledsDir.entryList(QStringList{ QStringLiteral("*::capslock") }, QDir::Dirs)) {
        const QString bright = ledsDir.filePath(entry + QStringLiteral("/brightness"));
        if (QFileInfo::exists(bright)) {
            m_capsLedPath = bright;
            break;
        }
    }

    const QDir devDir(QStringLiteral("/dev"));
    m_hasVideoDevices = !devDir.entryList(QStringList{ QStringLiteral("video*") }, QDir::System).isEmpty();
}

void SystemWatch::tick() {
    discoverPathsOnce();
    pollCapsLock();

    // Battery every 2 ticks, camera fd scan every 3 ticks (zero fork/exec)
    if (m_tickCounter % 2 == 0) {
        pollBattery();
    }
    if (m_tickCounter % 3 == 0) {
        pollCamera();
    }
    ++m_tickCounter;
}

void SystemWatch::pollBattery() {
    bool present = false;
    int pct = -1;
    QString status;
    bool charging = false;
    qreal watts = 0.0;
    bool onAc = true;

    if (!m_acDir.isEmpty()) {
        bool ok = false;
        const qint64 online = readInt64(m_acDir + QStringLiteral("/online"), &ok);
        if (ok) {
            onAc = (online != 0);
        }
    }

    if (!m_batteryDir.isEmpty()) {
        present = true;
        status = readTrimmed(m_batteryDir + QStringLiteral("/status"));
        charging = (status == QStringLiteral("Charging"));

        bool okNow = false;
        bool okFull = false;
        qint64 now = readInt64(m_batteryDir + QStringLiteral("/charge_now"), &okNow);
        qint64 full = readInt64(m_batteryDir + QStringLiteral("/charge_full"), &okFull);
        if (!okNow || !okFull || full <= 0) {
            now = readInt64(m_batteryDir + QStringLiteral("/energy_now"), &okNow);
            full = readInt64(m_batteryDir + QStringLiteral("/energy_full"), &okFull);
        }

        if (okNow && okFull && full > 0) {
            const double ratio = static_cast<double>(now) * 100.0 / static_cast<double>(full);
            pct = std::clamp(static_cast<int>(std::lround(ratio)), 0, 100);
        } else {
            bool okCap = false;
            const qint64 cap = readInt64(m_batteryDir + QStringLiteral("/capacity"), &okCap);
            if (okCap) {
                pct = std::clamp(static_cast<int>(cap), 0, 100);
            }
        }

        bool okPow = false;
        const qint64 powerNow = readInt64(m_batteryDir + QStringLiteral("/power_now"), &okPow);
        if (okPow && powerNow >= 0) {
            watts = std::round(static_cast<double>(powerNow) / 1e5) / 10.0;
        } else {
            bool okCur = false;
            bool okVolt = false;
            const qint64 cur = readInt64(m_batteryDir + QStringLiteral("/current_now"), &okCur);
            const qint64 volt = readInt64(m_batteryDir + QStringLiteral("/voltage_now"), &okVolt);
            if (okCur && okVolt) {
                const double w = (static_cast<double>(std::abs(cur)) / 1e6) * (static_cast<double>(std::abs(volt)) / 1e6);
                watts = std::round(w * 10.0) / 10.0;
            }
        }
    }

    if (present != m_batteryPresent || pct != m_batteryPercentage || status != m_batteryStatus ||
        charging != m_batteryCharging || std::abs(watts - m_batteryWatts) > 0.05 || onAc != m_onAcPower) {
        m_batteryPresent = present;
        m_batteryPercentage = pct;
        m_batteryStatus = status;
        m_batteryCharging = charging;
        m_batteryWatts = watts;
        m_onAcPower = onAc;
        emit batteryChanged();
    }
}

void SystemWatch::pollCapsLock() {
    if (m_capsLedPath.isEmpty()) {
        return;
    }
    bool ok = false;
    const qint64 val = readInt64(m_capsLedPath, &ok);
    if (!ok) {
        return;
    }
    const bool caps = (val != 0);
    if (caps != m_capsLock) {
        m_capsLock = caps;
        emit capsLockChanged();
    }
}

void SystemWatch::pollCamera() {
    if (!m_hasVideoDevices) {
        return;
    }

    bool active = false;
    DIR* procDir = opendir("/proc");
    if (procDir) {
        char fdDirPath[64];
        char fdLinkPath[128];
        char target[256];
        const uid_t myUid = getuid();
        Q_UNUSED(myUid);

        while (const dirent* entry = readdir(procDir)) {
            if (!isAllDigits(entry->d_name)) {
                continue;
            }
            const int n = std::snprintf(fdDirPath, sizeof(fdDirPath), "/proc/%s/fd", entry->d_name);
            if (n <= 0 || static_cast<size_t>(n) >= sizeof(fdDirPath)) {
                continue;
            }
            DIR* fdDir = opendir(fdDirPath);
            if (!fdDir) {
                continue;
            }
            while (const dirent* fdEntry = readdir(fdDir)) {
                if (fdEntry->d_name[0] == '.') {
                    continue;
                }
                const int m = std::snprintf(fdLinkPath, sizeof(fdLinkPath), "%s/%s", fdDirPath, fdEntry->d_name);
                if (m <= 0 || static_cast<size_t>(m) >= sizeof(fdLinkPath)) {
                    continue;
                }
                const ssize_t len = readlink(fdLinkPath, target, sizeof(target) - 1);
                if (len > 10) {
                    target[len] = '\0';
                    if (std::strncmp(target, "/dev/video", 10) == 0) {
                        active = true;
                        break;
                    }
                }
            }
            closedir(fdDir);
            if (active) {
                break;
            }
        }
        closedir(procDir);
    }

    if (active != m_cameraActive) {
        m_cameraActive = active;
        emit cameraActiveChanged();
    }
}

} // namespace anoshell::services
