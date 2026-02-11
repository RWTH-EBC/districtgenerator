#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vergleicht zwei große Textdateien zeilenweise und zeigt die Unterschiede an.
"""

import sys
from pathlib import Path

def compare_files(file1_path, file2_path, output_path=None):
    """
    Vergleicht zwei Dateien zeilenweise und gibt Unterschiede aus.
    
    Args:
        file1_path: Pfad zur ersten Datei
        file2_path: Pfad zur zweiten Datei
        output_path: Optionaler Pfad für Ausgabedatei (sonst Konsole)
    """
    
    print(f"Vergleiche:\n  Datei 1: {file1_path}\n  Datei 2: {file2_path}\n")
    
    differences = []
    line_num = 0
    file1_only = 0
    file2_only = 0
    different_lines = 0
    
    try:
        with open(file1_path, 'r', encoding='utf-8') as f1, \
             open(file2_path, 'r', encoding='utf-8') as f2:
            
            for line_num, (line1, line2) in enumerate(zip(f1, f2), 1):
                if line1 != line2:
                    different_lines += 1
                    differences.append({
                        'line': line_num,
                        'file1': line1.rstrip('\n'),
                        'file2': line2.rstrip('\n')
                    })
                
                # Fortschritt alle 100.000 Zeilen
                if line_num % 100000 == 0:
                    print(f"  Verarbeitet: {line_num:,} Zeilen...")
            
            # Prüfen ob eine Datei länger ist
            remaining1 = list(f1)
            remaining2 = list(f2)
            
            if remaining1:
                file1_only = len(remaining1)
                for i, line in enumerate(remaining1, 1):
                    differences.append({
                        'line': line_num + i,
                        'file1': line.rstrip('\n'),
                        'file2': '[NICHT VORHANDEN]'
                    })
            
            if remaining2:
                file2_only = len(remaining2)
                for i, line in enumerate(remaining2, 1):
                    differences.append({
                        'line': line_num + i,
                        'file1': '[NICHT VORHANDEN]',
                        'file2': line.rstrip('\n')
                    })
    
    except FileNotFoundError as e:
        print(f"Fehler: Datei nicht gefunden - {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Fehler beim Lesen der Dateien: {e}")
        sys.exit(1)
    
    # Ergebnisse ausgeben
    print(f"\n{'='*70}")
    print(f"VERGLEICH ABGESCHLOSSEN")
    print(f"{'='*70}")
    print(f"Gesamt verarbeitete Zeilen: {line_num:,}")
    print(f"Unterschiedliche Zeilen:    {different_lines:,}")
    print(f"Nur in Datei 1:             {file1_only:,}")
    print(f"Nur in Datei 2:             {file2_only:,}")
    print(f"Gesamt Unterschiede:        {len(differences):,}")
    print(f"{'='*70}\n")
    
    if differences:
        # Ausgabe der Unterschiede
        if output_path:
            write_differences_to_file(differences, output_path, file1_path, file2_path)
            print(f"Unterschiede wurden in '{output_path}' gespeichert.")
        else:
            # Zeige erste 50 Unterschiede in der Konsole
            max_show = 50
            print(f"Zeige erste {min(max_show, len(differences))} Unterschiede:\n")
            
            for i, diff in enumerate(differences[:max_show], 1):
                print(f"Zeile {diff['line']:,}:")
                print(f"  Datei 1: {diff['file1']}")
                print(f"  Datei 2: {diff['file2']}")
                print()
            
            if len(differences) > max_show:
                print(f"... und {len(differences) - max_show:,} weitere Unterschiede.")
                print(f"\nTipp: Führen Sie das Script mit einem Ausgabepfad aus,")
                print(f"      um alle Unterschiede in eine Datei zu speichern.")
    else:
        print("✓ Die Dateien sind identisch!")


def write_differences_to_file(differences, output_path, file1_path, file2_path):
    """Schreibt alle Unterschiede in eine Ausgabedatei."""
    with open(output_path, 'w', encoding='utf-8') as out:
        out.write(f"Vergleich von:\n")
        out.write(f"  Datei 1: {file1_path}\n")
        out.write(f"  Datei 2: {file2_path}\n")
        out.write(f"\nGesamt {len(differences):,} Unterschiede gefunden:\n")
        out.write("="*70 + "\n\n")
        
        for diff in differences:
            out.write(f"Zeile {diff['line']:,}:\n")
            out.write(f"  Datei 1: {diff['file1']}\n")
            out.write(f"  Datei 2: {diff['file2']}\n")
            out.write("\n")


def main():
    """Hauptfunktion mit Kommandozeilen-Interface."""
    
    if len(sys.argv) < 3:
        print("VERWENDUNG:")
        print(f"  python {sys.argv[0]} <datei1.txt> <datei2.txt> [ausgabe.txt]")
        print()
        print("BEISPIELE:")
        print(f"  python {sys.argv[0]} alte_version.txt neue_version.txt")
        print(f"  python {sys.argv[0]} alte_version.txt neue_version.txt unterschiede.txt")
        sys.exit(1)
    
    file1 = sys.argv[1]
    file2 = sys.argv[2]
    output = sys.argv[3] if len(sys.argv) > 3 else None
    
    compare_files(file1, file2, output)


if __name__ == "__main__":
    main()