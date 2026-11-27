#pragma once

#include "audioprovider.hpp"

#include <QVector>
#include <fftw3.h>
#include <qqmlintegration.h>
#include <vector>

namespace anoshell::services {

class CavaProcessor : public AudioProcessor {
    Q_OBJECT

public:
    explicit CavaProcessor(QObject* parent = nullptr);
    ~CavaProcessor() override;

    void setBars(int bars);

signals:
    void valuesChanged(QVector<double> values);

protected:
    void process() override;

private:
    static constexpr int kFftSize = 2048;
    static constexpr int kBins = kFftSize / 2 + 1;

    fftw_plan m_plan = nullptr;
    double* m_fftIn = nullptr;
    fftw_complex* m_fftOut = nullptr;

    std::vector<double> m_chunk;
    std::vector<double> m_ring;
    std::vector<double> m_window;
    std::vector<int> m_bandStart;
    std::vector<int> m_bandEnd;
    std::vector<double> m_bandWeight;
    std::vector<double> m_smooth;

    int m_bars = 0;
    double m_autoGain = 1.0;
    QVector<double> m_values;

    void rebuildBands();
    void initFft();
    void cleanupFft();
};

class CavaProvider : public AudioProvider {
    Q_OBJECT
    QML_ELEMENT

    Q_PROPERTY(int bars READ bars WRITE setBars NOTIFY barsChanged)
    Q_PROPERTY(QVector<double> values READ values NOTIFY valuesChanged)

public:
    explicit CavaProvider(QObject* parent = nullptr);

    [[nodiscard]] int bars() const;
    void setBars(int bars);

    [[nodiscard]] QVector<double> values() const;

signals:
    void barsChanged();
    void valuesChanged();

private:
    int m_bars = 0;
    QVector<double> m_values;

    void updateValues(QVector<double> values);
};

} // namespace anoshell::services
