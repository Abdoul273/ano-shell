#include "beattracker.hpp"

#include "audiocollector.hpp"
#include "audioprovider.hpp"

#include <algorithm>
#include <cmath>
#include <numeric>

namespace anoshell::services {

BeatProcessor::BeatProcessor(QObject* parent)
    : AudioProcessor(parent)
    , m_chunk(static_cast<size_t>(ac::CHUNK_SIZE), 0.0f) {}

void BeatProcessor::process() {
    const quint32 count = AudioCollector::instance().readChunk(m_chunk.data());
    if (count == 0) {
        return;
    }

    ++m_frameCount;

    double energySum = 0.0;
    for (quint32 i = 0; i < count; ++i) {
        const double s = static_cast<double>(m_chunk[static_cast<size_t>(i)]);
        energySum += s * s;
    }
    const float energy = static_cast<float>(energySum / static_cast<double>(count));

    double avgEnergy = 0.0;
    if (m_historyCount > 0) {
        for (size_t i = 0; i < m_historyCount; ++i) {
            avgEnergy += static_cast<double>(m_energyHistory[i]);
        }
        avgEnergy /= static_cast<double>(m_historyCount);
    }

    m_energyHistory[m_historyIdx] = energy;
    m_historyIdx = (m_historyIdx + 1) % kHistorySize;
    if (m_historyCount < kHistorySize) {
        ++m_historyCount;
    }

    // Refractory period ~260 ms (~230 BPM max)
    constexpr quint64 minFramesBetweenBeats = 22;
    const bool ready = m_historyCount >= 16 && (m_frameCount - m_lastBeatFrame) >= minFramesBetweenBeats;
    if (ready && static_cast<double>(energy) > 0.0004 && static_cast<double>(energy) > avgEnergy * 1.48) {
        if (m_lastBeatFrame > 0) {
            const quint64 deltaFrames = m_frameCount - m_lastBeatFrame;
            const double seconds = static_cast<double>(deltaFrames * ac::CHUNK_SIZE) / static_cast<double>(ac::SAMPLE_RATE);
            if (seconds >= 0.25 && seconds <= 1.25) {
                m_intervals[m_intervalIdx] = seconds;
                m_intervalIdx = (m_intervalIdx + 1) % kIntervalsSize;
                if (m_intervalCount < kIntervalsSize) {
                    ++m_intervalCount;
                }

                double sum = 0.0;
                for (size_t i = 0; i < m_intervalCount; ++i) {
                    sum += m_intervals[i];
                }
                const double avgSec = sum / static_cast<double>(m_intervalCount);
                const float instantBpm = std::clamp(static_cast<float>(60.0 / avgSec), 60.0f, 200.0f);
                m_currentBpm = m_currentBpm * 0.7f + instantBpm * 0.3f;
            }
        }
        m_lastBeatFrame = m_frameCount;
        emit beat(m_currentBpm);
    }
}

BeatTracker::BeatTracker(QObject* parent)
    : AudioProvider(parent)
    , m_bpm(120.0f) {
    m_processor = new BeatProcessor();
    init();

    connect(static_cast<BeatProcessor*>(m_processor), &BeatProcessor::beat, this, &BeatTracker::updateBpm);
}

float BeatTracker::bpm() const {
    return m_bpm;
}

void BeatTracker::updateBpm(float bpm) {
    emit beat(bpm);
    if (std::abs(bpm - m_bpm) > 0.25f) {
        m_bpm = bpm;
        emit bpmChanged();
    }
}

} // namespace anoshell::services
