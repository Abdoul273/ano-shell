#pragma once

#include "audioprovider.hpp"

#include <array>
#include <qqmlintegration.h>
#include <vector>

namespace anoshell::services {

class BeatProcessor : public AudioProcessor {
    Q_OBJECT

public:
    explicit BeatProcessor(QObject* parent = nullptr);
    ~BeatProcessor() override = default;

signals:
    void beat(float bpm);

protected:
    void process() override;

private:
    static constexpr size_t kHistorySize = 43; // ~0.5 s at 512 / 44100 Hz
    static constexpr size_t kIntervalsSize = 8;

    std::vector<float> m_chunk;
    std::array<float, kHistorySize> m_energyHistory{};
    std::array<double, kIntervalsSize> m_intervals{};
    size_t m_historyIdx = 0;
    size_t m_historyCount = 0;
    size_t m_intervalIdx = 0;
    size_t m_intervalCount = 0;
    quint64 m_frameCount = 0;
    quint64 m_lastBeatFrame = 0;
    float m_currentBpm = 120.0f;
};

class BeatTracker : public AudioProvider {
    Q_OBJECT
    QML_ELEMENT

    Q_PROPERTY(float bpm READ bpm NOTIFY bpmChanged)

public:
    explicit BeatTracker(QObject* parent = nullptr);

    [[nodiscard]] float bpm() const;

signals:
    void bpmChanged();
    void beat(float bpm);

private:
    float m_bpm = 120.0f;

    void updateBpm(float bpm);
};

} // namespace anoshell::services
