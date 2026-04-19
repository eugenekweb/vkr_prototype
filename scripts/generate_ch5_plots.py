"""
Генератор графиков для главы 5.
Алгоритмические сводки в `aggregated.csv` оказались одинаковыми внутри батчей,
поэтому графики строятся по сценариям и по стратегии назначения, где различия
действительно присутствуют.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

plt.rcParams['figure.figsize'] = (12, 7)
plt.rcParams['font.size'] = 11
plt.rcParams['font.family'] = 'DejaVu Sans'
plt.rcParams['axes.labelsize'] = 12
plt.rcParams['axes.titlesize'] = 13
plt.rcParams['xtick.labelsize'] = 10
plt.rcParams['ytick.labelsize'] = 10
plt.rcParams['legend.fontsize'] = 10
plt.rcParams['lines.linewidth'] = 2.0

RESULTS_DIR = Path('results/ch5')
OUTPUT_DIR = RESULTS_DIR / 'plots'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

BASELINE_BATCH = 'p2_baseline_wll'
ROUND_ROBIN_BATCH = 'p2_baseline_edf_round_robin'
CITO_BATCH = 'p3_cito_burst'
GROWTH_BATCH = 'p4_growth20'

BATCH_ORDER = [BASELINE_BATCH, ROUND_ROBIN_BATCH, CITO_BATCH, GROWTH_BATCH]
BATCH_LABELS = {
    BASELINE_BATCH: 'Базовый (WLL)',
    ROUND_ROBIN_BATCH: 'Базовый (round-robin)',
    CITO_BATCH: 'Всплеск CITO',
    GROWTH_BATCH: 'Рост +20% (λ=535)',
}
BATCH_COLORS = {
    BASELINE_BATCH: '#3498DB',
    ROUND_ROBIN_BATCH: '#9B59B6',
    CITO_BATCH: '#F39C12',
    GROWTH_BATCH: '#E74C3C',
}


def load_batch_data(batch_name: str):
    csv_file = RESULTS_DIR / batch_name / 'summary' / 'aggregated.csv'
    try:
        return pd.read_csv(csv_file)
    except FileNotFoundError as exc:
        print(f'Warning: {batch_name} not found: {exc}')
        return None


def batch_summary(batch_name: str, metric: str):
    df = load_batch_data(batch_name)
    if df is None or metric not in df.columns:
        return None

    values = df[metric].dropna()
    if values.empty:
        return None

    mean = float(values.mean())
    se = float(values.std(ddof=1) / np.sqrt(len(values))) if len(values) > 1 else 0.0
    ci = 1.96 * se
    return mean, se, ci


def metric_frame(metric: str, scale: float = 1.0):
    rows = []
    for batch_name in BATCH_ORDER:
        summary = batch_summary(batch_name, metric)
        if summary is None:
            continue
        mean, se, ci = summary
        rows.append({
            'batch': batch_name,
            'label': BATCH_LABELS[batch_name],
            'mean': mean * scale,
            'se': se * scale,
            'ci': ci * scale,
        })
    return pd.DataFrame(rows)


def plot_sla_comparison():
    fig, ax = plt.subplots(figsize=(11, 6))
    frame = metric_frame('sla_plan_target', scale=100)
    x = np.arange(len(frame))

    ax.bar(
        x,
        frame['mean'],
        yerr=frame['ci'],
        color=[BATCH_COLORS[b] for b in frame['batch']],
        alpha=0.85,
        capsize=5,
        edgecolor='black',
        linewidth=1.5,
    )
    ax.axhline(y=90, color='red', linestyle='--', linewidth=2, label='Цель 90%', alpha=0.7)
    ax.set_ylabel('Целевой SLA плановых заданий, % (SLA_plan_target)')
    ax.set_xlabel('Сценарий / стратегия')
    ax.set_ylim([0, 105])
    ax.set_xticks(x)
    ax.set_xticklabels(frame['label'], rotation=20, ha='right')
    ax.grid(axis='y', alpha=0.3, linestyle=':')
    ax.legend(loc='lower left')

    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / 'fig_5_1_sla_comparison.png', dpi=300, bbox_inches='tight')
    plt.close()
    print('✓ Saved: fig_5_1_sla_comparison.png')


def plot_tat_distribution():
    frame_med = metric_frame('tat_median_min')
    frame_p95 = metric_frame('tat_p95_min')

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
    x = np.arange(len(frame_med))

    ax1.bar(
        x,
        frame_med['mean'],
        yerr=frame_med['ci'],
        color=[BATCH_COLORS[b] for b in frame_med['batch']],
        alpha=0.85,
        capsize=5,
        edgecolor='black',
        linewidth=1.5,
    )
    ax1.set_ylabel('Минуты (TAT)')
    ax1.set_xticks(x)
    ax1.set_xticklabels(frame_med['label'], rotation=20, ha='right')
    ax1.grid(axis='y', alpha=0.3, linestyle=':')

    ax2.bar(
        x,
        frame_p95['mean'],
        yerr=frame_p95['ci'],
        color=[BATCH_COLORS[b] for b in frame_p95['batch']],
        alpha=0.85,
        capsize=5,
        edgecolor='black',
        linewidth=1.5,
    )
    ax2.set_ylabel('Минуты (TAT)')
    ax2.set_xticks(x)
    ax2.set_xticklabels(frame_p95['label'], rotation=20, ha='right')
    ax2.grid(axis='y', alpha=0.3, linestyle=':')

    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / 'fig_5_2_tat_distribution.png', dpi=300, bbox_inches='tight')
    plt.close()
    print('✓ Saved: fig_5_2_tat_distribution.png')


def plot_load_balance():
    fig, ax = plt.subplots(figsize=(11, 6))
    frame = metric_frame('sigma_w2')
    x = np.arange(len(frame))

    ax.bar(
        x,
        frame['mean'],
        yerr=frame['ci'],
        color=[BATCH_COLORS[b] for b in frame['batch']],
        alpha=0.85,
        capsize=5,
        edgecolor='black',
        linewidth=1.5,
    )
    ax.set_ylabel('Дисперсия нагрузки σ²_W')
    ax.set_xlabel('Сценарий / стратегия')
    ax.set_xticks(x)
    ax.set_xticklabels(frame['label'], rotation=20, ha='right')
    ax.grid(axis='y', alpha=0.3, linestyle=':')

    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / 'fig_5_3_load_balance.png', dpi=300, bbox_inches='tight')
    plt.close()
    print('✓ Saved: fig_5_3_load_balance.png')


def plot_robustness():
    fig, ax = plt.subplots(figsize=(11, 6))
    frame = metric_frame('sla_plan_target', scale=100)
    x = np.arange(len(frame))

    ax.bar(
        x,
        frame['mean'],
        yerr=frame['ci'],
        color=[BATCH_COLORS[b] for b in frame['batch']],
        alpha=0.85,
        capsize=5,
        edgecolor='black',
        linewidth=1.5,
    )
    ax.axhline(y=90, color='green', linestyle='--', linewidth=2, label='Цель 90%', alpha=0.7)
    ax.set_ylabel('Целевой SLA плановых заданий, % (SLA_plan_target)')
    ax.set_xlabel('Сценарий / стратегия')
    ax.set_ylim([0, 105])
    ax.set_xticks(x)
    ax.set_xticklabels(frame['label'], rotation=20, ha='right')
    ax.grid(axis='y', alpha=0.3, linestyle=':')
    ax.legend(loc='lower left')

    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / 'fig_5_4_robustness.png', dpi=300, bbox_inches='tight')
    plt.close()
    print('✓ Saved: fig_5_4_robustness.png')


def plot_cito_impact():
    base = batch_summary(BASELINE_BATCH, 'sla_plan_target')
    cito = batch_summary(CITO_BATCH, 'sla_plan_target')
    if base is None or cito is None:
        return

    base_mean, _, base_ci = base
    cito_mean, _, cito_ci = cito

    fig, ax = plt.subplots(figsize=(9, 6))
    labels = ['Базовый (WLL)', 'Всплеск CITO']
    means = [base_mean * 100, cito_mean * 100]
    cis = [base_ci * 100, cito_ci * 100]

    ax.bar(
        labels,
        means,
        yerr=cis,
        color=[BATCH_COLORS[BASELINE_BATCH], BATCH_COLORS[CITO_BATCH]],
        alpha=0.85,
        capsize=5,
        edgecolor='black',
        linewidth=1.5,
    )
    ax.axhline(y=90, color='red', linestyle='--', linewidth=2, label='Цель 90%', alpha=0.7)
    ax.set_ylabel('Целевой SLA плановых заданий, % (SLA_plan_target)')
    ax.set_ylim([0, 105])
    ax.grid(axis='y', alpha=0.3, linestyle=':')
    ax.legend(loc='lower left')

    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / 'fig_5_5_cito_impact.png', dpi=300, bbox_inches='tight')
    plt.close()
    print('✓ Saved: fig_5_5_cito_impact.png')


def plot_summary_heatmap():
    metrics = ['sla_plan_target', 'sla_plan_max', 'tat_median_min', 'sigma_w2', 'throughput_per_hour']
    frame = pd.DataFrame(index=metrics)

    for batch_name in BATCH_ORDER:
        df = load_batch_data(batch_name)
        if df is None:
            continue
        frame[BATCH_LABELS[batch_name]] = [df[metric].mean() for metric in metrics]

    normalized = frame.copy()
    normalized.loc['sla_plan_target'] = frame.loc['sla_plan_target']
    normalized.loc['sla_plan_max'] = frame.loc['sla_plan_max']
    normalized.loc['tat_median_min'] = 1 - (frame.loc['tat_median_min'] / frame.loc['tat_median_min'].max())
    normalized.loc['sigma_w2'] = 1 - (frame.loc['sigma_w2'] / frame.loc['sigma_w2'].max())
    normalized.loc['throughput_per_hour'] = frame.loc['throughput_per_hour'] / frame.loc['throughput_per_hour'].max()

    fig, ax = plt.subplots(figsize=(12, 6))
    sns.heatmap(
        normalized,
        annot=True,
        fmt='.2f',
        cmap='RdYlGn',
        cbar_kws={'label': 'Нормированная оценка'},
        vmin=0,
        vmax=1,
        linewidths=0.5,
        linecolor='gray',
        ax=ax,
        annot_kws={'fontsize': 10, 'fontweight': 'bold'},
    )
    ax.set_xlabel('Сценарий / стратегия')
    ax.set_ylabel('Метрика')

    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / 'fig_5_6_summary_heatmap.png', dpi=300, bbox_inches='tight')
    plt.close()
    print('✓ Saved: fig_5_6_summary_heatmap.png')


def plot_sla_cito_consistency():
    fig, ax = plt.subplots(figsize=(11, 6))
    frame = metric_frame('sla_cito', scale=100)
    x = np.arange(len(frame))

    ax.bar(
        x,
        frame['mean'],
        yerr=frame['ci'],
        color=[BATCH_COLORS[b] for b in frame['batch']],
        alpha=0.85,
        capsize=5,
        edgecolor='black',
        linewidth=1.5,
    )
    ax.set_ylabel('SLA_CITO, %')
    ax.set_xlabel('Сценарий / стратегия')
    ax.set_ylim([0, 15])
    ax.set_xticks(x)
    ax.set_xticklabels(frame['label'], rotation=20, ha='right')
    ax.grid(axis='y', alpha=0.3, linestyle=':')

    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / 'fig_5_7_sla_cito_check.png', dpi=300, bbox_inches='tight')
    plt.close()
    print('✓ Saved: fig_5_7_sla_cito_check.png')


def main():
    print('=' * 70)
    print('Chapter 5: Scenario-based plot generation')
    print('=' * 70)
    print()

    try:
        print('1. Generating SLA comparison plots...')
        plot_sla_comparison()

        print('2. Generating TAT distribution plots...')
        plot_tat_distribution()

        print('3. Generating load balance plots...')
        plot_load_balance()

        print('4. Generating robustness plots...')
        plot_robustness()

        print('5. Generating CITO impact plots...')
        plot_cito_impact()

        print('6. Generating summary heatmap...')
        plot_summary_heatmap()

        print('7. Generating SLA_CITO consistency check...')
        plot_sla_cito_consistency()

        print()
        print('=' * 70)
        print('✓ ALL PLOTS GENERATED SUCCESSFULLY')
        print(f'  Output directory: {OUTPUT_DIR}')
        print('=' * 70)
    except Exception as exc:
        print(f'✗ ERROR: {exc}')
        import traceback

        traceback.print_exc()


if __name__ == '__main__':
    main()
