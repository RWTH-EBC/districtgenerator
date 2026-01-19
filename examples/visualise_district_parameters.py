import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np


def plot_metric_comparison(path_sim, path_real, target_metric):
    # 1. Daten einlesen
    df_sim = pd.read_csv(path_sim)
    df_real = pd.read_csv(path_real, sep=';')

    # Herkunft markieren
    df_sim['Quelle'] = 'Typquartiere'
    df_real['Quelle'] = 'Realdaten'

    # Filter auf die gewünschte Metrik
    df_sim_metric = df_sim[df_sim['metric'] == target_metric]
    df_real_metric = df_real[df_real['metric'] == target_metric]

    if df_sim_metric.empty or df_real_metric.empty:
        print(f"Metrik '{target_metric}' nicht in den Daten gefunden.")
        return

    # 2. Daten für Boxplot umstrukturieren
    # Erstelle synthetische Datenpunkte aus min/max/mean
    data_for_plot = []

    for _, row in pd.concat([df_sim_metric, df_real_metric]).iterrows():
        # Verwende min, mean, max als drei "Datenpunkte"
        for value in [row['min'], row['mean'], row['max']]:
            data_for_plot.append({
                'typ': row['typ'],
                'Quelle': row['Quelle'],
                'value': value
            })

    df_plot = pd.DataFrame(data_for_plot)

    # 3. Boxplot erstellen
    plt.figure(figsize=(14, 7))
    sns.set_style("whitegrid")

    # Sortiere Typen alphabetisch
    order = sorted(df_plot['typ'].unique())

    ax = sns.boxplot(
        data=df_plot,
        x='typ',
        y='value',
        hue='Quelle',
        order=order,
        palette='Set2',
        showfliers=False,
        width=0.4
    )

    """# Optionale Punkte über den Boxen anzeigen
    sns.stripplot(
        data=df_plot,
        x='typ',
        y='value',
        hue='Quelle',
        order=order,
        dodge=True,
        palette='dark:black',
        alpha=0.6,
        ax=ax,
        legend=False
    )"""

    # plt.title(f'Vergleich: {target_metric} (Simulation vs. Echt-Daten)', fontsize=14, fontweight='bold')
    ax.tick_params(axis='both', labelsize=14)
    plt.ylabel(target_metric, fontsize=14)
    plt.xlabel('Quartierstyp', fontsize=14)
    plt.legend(fontsize=14) #, title='Datensatz', title_fontsize=14)

    plt.tight_layout()
    plt.show()


# Beispielaufruf
plot_metric_comparison('quartiere_typen_statistik.csv', 'parameter_csv.csv', 'building_coverage_ratio')