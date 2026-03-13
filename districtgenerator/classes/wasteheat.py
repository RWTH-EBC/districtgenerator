import matplotlib.pyplot as plt
import numpy as np

# -----------------------------
# Daten
# -----------------------------

LCOH_decentral = 0.2823
LCOH_central = 0.2716

distances = [300, 400, 500]
LCOH_wh = [0.2548, 0.259, 0.2765]

labels = [
    "Zentral",
    "300 m",
    "400 m",
    "500 m"
]

CAPEX = [155542, 163004, 165726, 185381]
OPEX = [143123, 117172, 114470, 118629]

# -----------------------------
# Plot 1: LCOH vs Entfernung
# -----------------------------

plt.figure(figsize=(8,5))

# horizontale Linien
plt.axhline(LCOH_decentral, linestyle="-", color="blue", label="dezentrale Versorgung")
plt.axhline(LCOH_central, linestyle="-", color="green", label="zentrale Versorgung")

# Punkte für Abwärme
plt.scatter(distances, LCOH_wh, color="red", s=80, label="zentrale Versorgung + Abwärmequelle")

# Beschriftung der Punkte
for i, d in enumerate(distances):
    plt.text(d, LCOH_wh[i] + 0.001, f"{d} m", ha="center")

plt.xlabel("Entfernung zum Quartier [m]")
plt.ylabel("LCOH")

# weiter ausgezoomte Achsen
plt.xlim(200, 600)
plt.ylim(0.24, 0.30)

plt.title("LCOH in Abhängigkeit der Distanz der Abwärmequelle")

# Legende rechts außerhalb
plt.legend(loc="center left", bbox_to_anchor=(1, 0.5))

plt.grid(True)

plt.tight_layout()
plt.show()


# -----------------------------
# Plot 2: CAPEX / OPEX Balken
# -----------------------------

x = np.arange(len(labels))

plt.figure(figsize=(8,5))

plt.bar(x, CAPEX, color="red", label="fixed")
plt.bar(x, OPEX, bottom=CAPEX, color="green", label="operational")

plt.xticks(x, labels)
plt.ylabel("TAC")
plt.title("Kostenstruktur verschiedener Szenarien")

# Legende rechts außerhalb
plt.legend(loc="center left", bbox_to_anchor=(1, 0.5))

plt.tight_layout()
plt.show()
