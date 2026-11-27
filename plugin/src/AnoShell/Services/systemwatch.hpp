#pragma once

#include <qtimer.h>

#include "tickingservice.hpp"

#include <qqmlintegration.h>

namespace anoshell::services {

class SystemWatch : public TickingService {
    Q_OBJECT
    QML_ELEMENT
    QML_SINGLETON

    Q_PROPERTY(bool batteryPresent READ batteryPresent NOTIFY batteryChanged)
    Q_PROPERTY(int batteryPercentage READ batteryPercentage NOTIFY batteryChanged)
    Q_PROPERTY(QString batteryStatus READ batteryStatus NOTIFY batteryChanged)
    Q_PROPERTY(bool batteryCharging READ batteryCharging NOTIFY batteryChanged)
    Q_PROPERTY(qreal batteryWatts READ batteryWatts NOTIFY batteryChanged)
    Q_PROPERTY(bool onAcPower READ onAcPower NOTIFY batteryChanged)
    Q_PROPERTY(bool capsLock READ capsLock NOTIFY capsLockChanged)
    Q_PROPERTY(bool cameraActive READ cameraActive NOTIFY cameraActiveChanged)

public:
    explicit SystemWatch(QObject* parent = nullptr);

    [[nodiscard]] bool batteryPresent() const;
    [[nodiscard]] int batteryPercentage() const;
    [[nodiscard]] QString batteryStatus() const;
    [[nodiscard]] bool batteryCharging() const;
    [[nodiscard]] qreal batteryWatts() const;
    [[nodiscard]] bool onAcPower() const;
    [[nodiscard]] bool capsLock() const;
    [[nodiscard]] bool cameraActive() const;

    Q_INVOKABLE void refreshNow();

signals:
    void batteryChanged();
    void capsLockChanged();
    void cameraActiveChanged();

protected:
    void tick() override;

private:
    void discoverPathsOnce();
    void pollBattery();
    void pollCapsLock();
    void pollCamera();

    bool m_discovered = false;
    QString m_batteryDir;
    QString m_acDir;
    QString m_capsLedPath;
    bool m_hasVideoDevices = false;

    bool m_batteryPresent = false;
    int m_batteryPercentage = -1;
    QString m_batteryStatus;
    bool m_batteryCharging = false;
    qreal m_batteryWatts = 0.0;
    bool m_onAcPower = true;
    bool m_capsLock = false;
    bool m_cameraActive = false;
    int m_tickCounter = 0;
};

} // namespace anoshell::services
