import numpy as np
import matplotlib.pyplot as plt
def pinch_basic():
    Q_cold = np.linspace(0, 10, 100)
    Q_hot = np.linspace(0, 8, 80)

    # Hot Stream
    T_hot = 95 - 3 * Q_hot

    # Cold Stream
    T_cold = 80 - 1.25 * Q_cold

    shift = 2
    Q_hot = Q_hot + shift

    plt.figure(figsize=(8, 6))
    plt.plot(Q_hot, T_hot, label='heißer Strom', color='red', linewidth=2)
    plt.plot(Q_cold, T_cold, label='kalter Strom', color='blue', linewidth=2)

    plt.xlabel("ΔQ [kWh]")
    plt.ylabel("Temperatur [°C]")
    plt.grid(True)
    plt.legend()

    xmin = min(Q_cold)
    xmax = max(Q_cold)
    xrange = xmax - xmin
    plt.xlim(xmin - 0.3*xrange, xmax + 0.7*xrange)

    plt.gca().set_xticklabels([])
    plt.gca().set_yticklabels([])
    ax = plt.gca()
    ax.xaxis.set_label_coords(0.95, -0.05)
    ax.yaxis.set_label_coords(-0.05, 0.9)

    plt.savefig("streams_einfach.pdf", format='pdf', dpi=300, bbox_inches='tight')
    plt.show()

def hot_streams():
    Q1 = np.linspace(0, 3, 100)
    Q2 = np.linspace(4, 6, 100)
    Q3 = np.linspace(7, 13, 100)

    # Temperaturen
    T_hot1 = 150 - 8 * (Q1 - Q1[0])
    T_hot2 = 135 - 6 * (Q2 - Q2[0])
    T_hot3 = 130 - 2 * (Q3 - Q3[0])

    plt.figure(figsize=(8, 6))

    plt.plot(Q1, T_hot1, color='red', linewidth=2, label='Hot Stream 1')
    plt.plot(Q2, T_hot2, color='red', linewidth=2, label='Hot Stream 2')
    plt.plot(Q3, T_hot3, color='red', linewidth=2, label='Hot Stream 3')

    plt.xlabel("ΔQ [kWh]")
    plt.ylabel("Temperatur [°C]")
    plt.grid(True)
    #plt.legend()

    plt.gca().set_xticklabels([])
    plt.gca().set_yticklabels([])

    plt.savefig("hot_streams_separate.pdf", format='pdf', dpi=300, bbox_inches='tight')
    plt.show()

def composite_curve():
    Q1 = np.linspace(0, 3, 100)
    Q2 = np.linspace(4, 6, 100)
    Q3 = np.linspace(7, 13, 100)

    # Temperaturen
    T_hot1 = 150 - 8 * (Q1 - Q1[0])
    T_hot2 = 135 - 6 * (Q2 - Q2[0])
    T_hot3 = 130 - 2 * (Q3 - Q3[0])

    plt.figure(figsize=(8, 6))
    # Original Streams plotten
    #plt.plot(Q1, T_hot1, color='red', linewidth=2, label='Hot Stream 1')
    #plt.plot(Q2, T_hot2, color='red', linewidth=2, label='Hot Stream 2')
    #plt.plot(Q3, T_hot3, color='red', linewidth=2, label='Hot Stream 3')

    plt.xlabel("ΔQ [kWh]")
    plt.ylabel("Temperatur [°C]")
    plt.grid(True)
    plt.gca().set_xticklabels([])
    plt.gca().set_yticklabels([])

    # --- Composite Curve berechnen ---
    # Steigungen (Cp) der Streams
    cp1 = 8
    cp2 = 6
    cp3 = 2

    # Alle relevanten Temperaturen sammeln
    temps = np.concatenate([T_hot1, T_hot2, T_hot3])
    temps_unique = np.unique(temps)
    temps_sorted = np.sort(temps_unique)[::-1]  # absteigend, wie üblich

    Q_comp = [0]  # Start bei Q=0
    T_comp = [temps_sorted[0]]

    # Schrittweise durch Temperaturintervalle
    for i in range(1, len(temps_sorted)):
        T_top = temps_sorted[i - 1]
        T_bottom = temps_sorted[i]
        dT = T_top - T_bottom

        # Prüfen, welche Streams im Intervall aktiv sind
        cp_sum = 0
        if T_top <= max(T_hot1) and T_bottom >= min(T_hot1):
            cp_sum += cp1
        if T_top <= max(T_hot2) and T_bottom >= min(T_hot2):
            cp_sum += cp2
        if T_top <= max(T_hot3) and T_bottom >= min(T_hot3):
            cp_sum += cp3
        dQ = cp_sum * dT
        Q_comp.append(Q_comp[-1] + dQ)
        T_comp.append(T_bottom)

    # Composite Curve plotten
    plt.plot(Q_comp, T_comp, color='red', linewidth=2, label='Composite Curve')
    plt.legend()

    plt.savefig("hot_streams_composite.pdf", format='pdf', dpi=300, bbox_inches='tight')
    plt.show()

x = composite_curve()