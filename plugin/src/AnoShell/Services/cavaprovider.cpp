#include "cavaprovider.hpp"

#include "audiocollector.hpp"
#include "audioprovider.hpp"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <numbers>
#include <qloggingcategory.h>

Q_LOGGING_CATEGORY(lcCava, "anoshell.services.cava", QtInfoMsg)
Q_LOGGING_CATEGORY(lcCavaProcessor, "anoshell.services.cava.processor", QtInfoMsg)

namespace anoshell::services {

namespace {

[[nodiscard]] bool vectorsDiffer(const QVector<double>& a, const QVector<double>& b) {
    if (a.size() != b.size()) {
        return true;
    }
    for (qsizetype i = 0; i < a.size(); ++i) {
        if (std::abs(a[i] - b[i]) > 1e-3) {
            return true;
        }
    }
    return false;
}

} // namespace

CavaProcessor::CavaProcessor(QObject* parent)
    : AudioProcessor(parent)
    , m_chunk(static_cast<size_t>(ac::CHUNK_SIZE), 0.0)
    , m_ring(static_cast<size_t>(kFftSize), 0.0)
    , m_window(static_cast<size_t>(kFftSize), 0.0) {
    constexpr double twoPi = 2.0 * std::numbers::pi;
    for (int i = 0; i < kFftSize; ++i) {
        const double denom = static_cast<double>(kFftSize - 1);
        m_window[static_cast<size_t>(i)] = 0.5 * (1.0 - std::cos(twoPi * static_cast<double>(i) / denom));
    }
    initFft();
}

CavaProcessor::~CavaProcessor() {
    cleanupFft();
}

void CavaProcessor::initFft() {
    if (m_plan) {
        return;
    }
    m_fftIn = fftw_alloc_real(static_cast<size_t>(kFftSize));
    m_fftOut = fftw_alloc_complex(static_cast<size_t>(kBins));
    if (m_fftIn && m_fftOut) {
        m_plan = fftw_plan_dft_r2c_1d(kFftSize, m_fftIn, m_fftOut, FFTW_ESTIMATE);
    }
}

void CavaProcessor::cleanupFft() {
    if (m_plan) {
        fftw_destroy_plan(m_plan);
        m_plan = nullptr;
    }
    if (m_fftIn) {
        fftw_free(m_fftIn);
        m_fftIn = nullptr;
    }
    if (m_fftOut) {
        fftw_free(m_fftOut);
        m_fftOut = nullptr;
    }
}

void CavaProcessor::rebuildBands() {
    const auto n = static_cast<size_t>(m_bars);
    m_bandStart.assign(n, 0);
    m_bandEnd.assign(n, 0);
    m_bandWeight.assign(n, 1.0);
    m_smooth.assign(n, 0.0);

    if (m_bars <= 0) {
        return;
    }

    constexpr double minFreq = 50.0;
    constexpr double maxFreq = 10000.0;
    const double sr = static_cast<double>(ac::SAMPLE_RATE);
    const double binHz = sr / static_cast<double>(kFftSize);
    const double ratio = maxFreq / minFreq;

    int prevEnd = 1;
    for (int i = 0; i < m_bars; ++i) {
        const double t0 = static_cast<double>(i) / static_cast<double>(m_bars);
        const double t1 = static_cast<double>(i + 1) / static_cast<double>(m_bars);
        const double f0 = minFreq * std::pow(ratio, t0);
        const double f1 = minFreq * std::pow(ratio, t1);

        int b0 = std::max(prevEnd, static_cast<int>(std::floor(f0 / binHz)));
        int b1 = std::max(b0 + 1, static_cast<int>(std::ceil(f1 / binHz)));
        b0 = std::clamp(b0, 1, kBins - 1);
        b1 = std::clamp(b1, b0 + 1, kBins);
        prevEnd = b0;

        const auto idx = static_cast<size_t>(i);
        m_bandStart[idx] = b0;
        m_bandEnd[idx] = b1;
        // Slight tilt so highs remain visible alongside bass energy
        m_bandWeight[idx] = 0.75 + 0.85 * t0;
    }
}

void CavaProcessor::process() {
    if (!m_plan || m_bars <= 0) {
        return;
    }

    const quint32 count = AudioCollector::instance().readChunk(m_chunk.data());
    if (count == 0) {
        return;
    }

    const auto shift = static_cast<size_t>(std::min<quint32>(count, static_cast<quint32>(kFftSize)));
    std::move(m_ring.begin() + static_cast<std::ptrdiff_t>(shift), m_ring.end(), m_ring.begin());
    std::copy(m_chunk.begin(), m_chunk.begin() + static_cast<std::ptrdiff_t>(shift), m_ring.end() - static_cast<std::ptrdiff_t>(shift));

    for (int i = 0; i < kFftSize; ++i) {
        const auto idx = static_cast<size_t>(i);
        m_fftIn[i] = m_ring[idx] * m_window[idx];
    }

    fftw_execute(m_plan);

    std::vector<double> raw(static_cast<size_t>(m_bars), 0.0);
    double frameMax = 0.0;
    const double normScale = 1.0 / static_cast<double>(kFftSize);

    for (int i = 0; i < m_bars; ++i) {
        const auto idx = static_cast<size_t>(i);
        const int b0 = m_bandStart[idx];
        const int b1 = m_bandEnd[idx];
        double peak = 0.0;
        for (int b = b0; b < b1; ++b) {
            const double re = m_fftOut[b][0];
            const double im = m_fftOut[b][1];
            const double mag = std::sqrt(re * re + im * im) * normScale;
            if (mag > peak) {
                peak = mag;
            }
        }
        const double weighted = std::sqrt(peak) * m_bandWeight[idx];
        raw[idx] = weighted;
        if (weighted > frameMax) {
            frameMax = weighted;
        }
    }

    // Automatic gain control with noise floor
    if (frameMax > 0.004) {
        const double targetGain = 0.85 / std::max(frameMax, 0.04);
        const double alpha = (targetGain < m_autoGain) ? 0.25 : 0.03;
        m_autoGain = m_autoGain * (1.0 - alpha) + targetGain * alpha;
        m_autoGain = std::clamp(m_autoGain, 0.25, 18.0);
    }

    // Temporal smoothing (fast attack, smooth gravity decay)
    for (int i = 0; i < m_bars; ++i) {
        const auto idx = static_cast<size_t>(i);
        double level = (raw[idx] > 0.002) ? std::clamp(raw[idx] * m_autoGain, 0.0, 1.0) : 0.0;
        const double prev = m_smooth[idx];
        if (level > prev) {
            level = prev * 0.35 + level * 0.65;
        } else {
            level = prev * 0.82 + level * 0.18;
            if (level < 0.002) {
                level = 0.0;
            }
        }
        m_smooth[idx] = level;
    }

    // Monstercat spatial smoothing filter
    QVector<double> values(m_bars);
    constexpr double inv = 1.0 / 1.5;
    double carry = 0.0;
    for (int i = 0; i < m_bars; ++i) {
        carry = std::max(m_smooth[static_cast<size_t>(i)], carry * inv);
        values[i] = carry;
    }
    carry = 0.0;
    for (int i = m_bars - 1; i >= 0; --i) {
        carry = std::max(m_smooth[static_cast<size_t>(i)], carry * inv);
        values[i] = std::max(values[i], carry);
    }

    if (vectorsDiffer(values, m_values)) {
        m_values = std::move(values);
        emit valuesChanged(m_values);
    }
}

void CavaProcessor::setBars(int bars) {
    if (bars < 0) {
        qCWarning(lcCavaProcessor) << "setBars: bars must be >= 0. Setting to 0.";
        bars = 0;
    }

    if (m_bars != bars) {
        m_bars = bars;
        m_values.clear();
        rebuildBands();
    }
}

CavaProvider::CavaProvider(QObject* parent)
    : AudioProvider(parent)
    , m_bars(0)
    , m_values(m_bars, 0.0) {
    m_processor = new CavaProcessor();
    init();

    connect(static_cast<CavaProcessor*>(m_processor), &CavaProcessor::valuesChanged, this, &CavaProvider::updateValues);
}

int CavaProvider::bars() const {
    return m_bars;
}

void CavaProvider::setBars(int bars) {
    if (bars < 0) {
        qCWarning(lcCava) << "setBars: bars must be >= 0. Setting to 0.";
        bars = 0;
    }

    if (m_bars == bars) {
        return;
    }

    m_values.resize(bars, 0.0);
    m_bars = bars;
    emit barsChanged();
    emit valuesChanged();

    QMetaObject::invokeMethod(
        static_cast<CavaProcessor*>(m_processor), &CavaProcessor::setBars, Qt::QueuedConnection, bars);
}

QVector<double> CavaProvider::values() const {
    return m_values;
}

void CavaProvider::updateValues(QVector<double> values) {
    if (vectorsDiffer(values, m_values)) {
        m_values = std::move(values);
        emit valuesChanged();
    }
}

} // namespace anoshell::services
