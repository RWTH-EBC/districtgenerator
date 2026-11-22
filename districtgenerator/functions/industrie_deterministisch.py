# -*- coding: utf-8 -*-
"""
WH1 Deterministik – konsolidierte Ein-Datei-Fassung (V7).

Basierend auf den sieben aktiven Deterministik-Modulen V4/V5/V6 und G20-Hydraulikfix.
Enthaelt Physik, Einzelquellen, Mehrquellen-HX, Dubletten, Gurobi-Bounds,
Pyomo-Integration und EHDO-Runner – ohne industrie_advanced_*-Imports.

Zur Kollisionsfreiheit besitzt jeder Originalbaustein einen privaten
Funktions-Namensraum. Dadurch bleiben z.B. die beiden verschiedenen
_technical_max()- und _make()-Implementierungen exakt erhalten.
Die Initialisierung fuehrt keine Optimierung aus.

Nur oeffentliche Funktionen am Dateiende von aussen aufrufen:
from_data, generate, run_all, execute, add_design, add_operation,
design_result, operating_result.t

WICHTIG: blaue Bestandsdateien benoetigen den in der Anleitung beschriebenen
Importtausch. Die industrie_optimierung_bridge und EHDO/Netzcodes bleiben
als eigenstaendige BESTANDSMODULE erforderlich.
"""
from __future__ import annotations
from types import SimpleNamespace as _DetNamespace

# ===========================================================================
# Originalbaustein: industrie_deterministisch_physik.py
# ===========================================================================
def _init_physik():
    # -*- coding: utf-8 -*-
    """Eigenstaendige thermische Grundbausteine fuer WH1 Deterministik.

    WICHTIG: KEINE Imports aus industrie_advanced_* ! Advanced kann spaeter
    vollstaendig entfernt werden, ohne diese Varianten anzufassen.

    Q2 (Dampf/Kondensat) und Q6 (Verfluessiger) werden nur als sensible
    Ersatzstroeme modelliert, nicht phasenaufgeloest. Kosten/U sind vorlaeufig.
    """
    from dataclasses import dataclass
    from math import log,isfinite

    HX_U_W_M2K_BY_CLASS={
        'Q1':900.0,'Q2':1800.0,'Q3':90.0,'Q4':75.0,
        'Q5':150.0,'Q6':900.0,'Q7':150.0,
    }
    HX_INV_EUR_M2_BY_CLASS={q:1200. for q in HX_U_W_M2K_BY_CLASS}
    HX_OM_EUR_A_BY_CLASS={q:1000. for q in HX_U_W_M2K_BY_CLASS}
    HX_LIFETIME_A_BY_CLASS={q:20 for q in HX_U_W_M2K_BY_CLASS}
    HX_APPROACH_K=5.0
    HP_EVAP_APPROACH_K=5.0
    HP_COND_APPROACH_K=5.0
    HP_ETA_CARNOT=0.40
    HP_COP_MIN=1.05
    HP_COP_MAX=8.0

    @dataclass(frozen=True)
    class HXState:
        area_m2_per_kW: float
        lmtd_K: float
        hot_in_C: float
        hot_out_C: float
        cold_in_C: float
        cold_out_C: float


    def lmtd(d_hot_K,d_cold_K):
        a=float(d_hot_K); b=float(d_cold_K)
        if not (isfinite(a) and isfinite(b) and a>0 and b>0):
            raise ValueError('DET-LMTD: beide Enddifferenzen muessen positiv sein')
        return (a+b)/2 if abs(a-b)<1e-10*max(a,b) else (a-b)/log(a/b)


    def hx_state(s,qcode,t_hot_in,t_hot_out,t_cold_in,t_cold_out,approach_K=HX_APPROACH_K):
        if not (t_hot_in>t_hot_out and t_cold_out>t_cold_in):return None
        d_hot=float(t_hot_in)-float(t_cold_out)
        d_cold=float(t_hot_out)-float(t_cold_in)
        if min(d_hot,d_cold) < approach_K-1e-8:return None
        u=float(HX_U_W_M2K_BY_CLASS[qcode])/1000.  # kW/(m² K)
        x=lmtd(d_hot,d_cold)
        return HXState(1./(u*x),x,float(t_hot_in),float(t_hot_out),
                       float(t_cold_in),float(t_cold_out))


    def hp_cop(t_source_out_C,t_heating_water_out_C):
        tev=float(t_source_out_C)-HP_EVAP_APPROACH_K+273.15
        tcd=float(t_heating_water_out_C)+HP_COND_APPROACH_K+273.15
        if not (isfinite(tev) and isfinite(tcd)) or tcd<=tev:
            raise ValueError('DET-WP: kein positiver Temperaturhub')
        cop=HP_ETA_CARNOT*tcd/(tcd-tev)
        return min(HP_COP_MAX,max(HP_COP_MIN,cop))
    return _DetNamespace(**locals())
_physik = _init_physik()
del _init_physik

# ===========================================================================
# Originalbaustein: industrie_deterministisch_varianten.py
# ===========================================================================
def _init_varianten():
    # -*- coding: utf-8 -*-
    """WH1-Modus 'deterministic': technische Variantenbibliothek (ohne Pyomo).

    Eine Variante ist eine physikalisch gepruefte, ueber 8760 Stunden vorberechnete
    ANLAGENKONFIGURATION, keine vorab erzwungene Waermeeinspeisung. EHDO darf
    zwischen 0 und dem angebotenen Waermestrom stetig waehlen.

    Einfache sensible Quellenapproximation: Cdot=PFA/(Tin-Tamb). Ein Betriebspunkt
    wird bei Teillast durch anteiligen Quellen-/Wasserstrom realisiert, also mit
    unveraenderten Temperaturen und COP; keine echte Teillastkennlinie.
    """

    from dataclasses import dataclass, field
    from math import isfinite
    from typing import Callable
    import warnings

    import numpy as np
    th = _physik

    SIZE_FACTORS = (0.50, 0.70, 0.90, 1.10)
    # Es ist wissenschaftlich wichtig, die Luft-WP nicht als kostenlose separate
    # Industrie-WP zu installieren. Sie ist nur bei manueller DualSource-Freigabe erlaubt.
    ALLOW_AIR_ONLY_WITH_DUALSOURCE = True
    # Feste WP-/HX-Regeln; pro Variante konfigurierbar, ohne den EHDO zu veraendern.
    APPROACH_K = 5.0
    MIN_TEMPERATURE_RISE_K = 0.1
    NUMERIC_EPS = 1e-8


    @dataclass
    class Variant:
        id: str
        family: str
        source_id: int  # -1 = Nullvariante
        factor: float
        heat_cap_kW: float
        hx_area_m2: float
        wp_cap_kW: float
        wp_kind: str  # none, normal, dual
        annual_hx_cost_EUR_a: float
        hx_investment_EUR: float
        hx_om_EUR_a: float
        heat_max_kW: np.ndarray = field(repr=False)
        el_per_heat: np.ndarray = field(repr=False)
        direct_fraction: np.ndarray = field(repr=False)
        notes: str = ''
        air_share: np.ndarray = field(default_factory=lambda: np.array([], dtype=float),repr=False)
        # Erweiterte Mehrquellen-Informationen. Leer => alte Einzelquellen-Variante.
        # Alle Quellenindizes beziehen sich auf die unveraenderte WH1-Eingangsreihenfolge.
        hx_areas_by_source_m2: tuple = ()
        hx_investment_by_source_EUR: tuple = ()
        hx_om_by_source_EUR_a: tuple = ()
        hx_annual_by_source_EUR_a: tuple = ()
        direct_fraction_by_source: np.ndarray = field(
            default_factory=lambda: np.empty((0, 0), dtype=float), repr=False)
        wp_industry_source_id: int = -1
        included_source_ids: tuple = ()
        excluded_source_ids: tuple = ()
        hx_order_water: tuple = ()
        strategy: str = 'direct_first'

        def per_source_arrays(self, S):
            """Fuer die EHDO: Kosten, Flaeche und Direktanteile pro ORIGINALQUELLE."""
            if self.hx_areas_by_source_m2:
                if any(len(x) != S for x in (
                        self.hx_areas_by_source_m2,
                        self.hx_investment_by_source_EUR,
                        self.hx_om_by_source_EUR_a,
                        self.hx_annual_by_source_EUR_a)):
                    raise ValueError('DET: Mehrquellen-Kostenvektoren haben falsche Laenge')
                frac = np.asarray(self.direct_fraction_by_source, dtype=float)
                if frac.shape != (S, len(self.heat_max_kW)):
                    raise ValueError('DET: direkte Quellenprofile haben falsche Form')
                if not np.allclose(frac.sum(axis=0), self.direct_fraction, atol=1e-8):
                    raise ValueError('DET: direkte Quellenanteile summieren sich falsch')
                return (np.asarray(self.hx_areas_by_source_m2, dtype=float),
                        np.asarray(self.hx_investment_by_source_EUR, dtype=float),
                        np.asarray(self.hx_om_by_source_EUR_a, dtype=float),
                        np.asarray(self.hx_annual_by_source_EUR_a, dtype=float), frac)
            area=np.zeros(S); inv=np.zeros(S); om=np.zeros(S); ann=np.zeros(S)
            frac=np.zeros((S,len(self.heat_max_kW)))
            if self.source_id>=0:
                if self.source_id>=S: raise ValueError('DET: Quellenindex ausserhalb der Quelleingabe')
                area[self.source_id]=self.hx_area_m2
                inv[self.source_id]=self.hx_investment_EUR
                om[self.source_id]=self.hx_om_EUR_a
                ann[self.source_id]=self.annual_hx_cost_EUR_a
                frac[self.source_id,:]=self.direct_fraction
            return area,inv,om,ann,frac

        def summary(self):
            # Die Betriebsstunden sind technische STUNDENPOTENZIALE aus der
            # 8760-h-Vorberechnung, NICHT der optimierte EHDO-Waermeabruf.
            wp_heat=np.maximum(0.,np.asarray(self.heat_max_kW,dtype=float)*
                                (1.-np.asarray(self.direct_fraction,dtype=float)))
            air=(np.asarray(self.air_share,dtype=float)>0.5
                 if len(self.air_share) else np.zeros(wp_heat.shape,dtype=bool))
            wp_active=wp_heat>1e-8
            return dict(id=self.id, family=self.family, source_id=self.source_id,
                        factor=self.factor, heat_cap_kW=self.heat_cap_kW,
                        hx_area_m2=self.hx_area_m2, wp_cap_kW=self.wp_cap_kW,
                        wp_kind=self.wp_kind, hx_investment_EUR=self.hx_investment_EUR,
                        annual_hx_cost_EUR_a=self.annual_hx_cost_EUR_a,
                        yearly_heat_potential_MWh=float(self.heat_max_kW.sum()/1000),
                        full_load_electric_MWh=float(np.sum(self.heat_max_kW*self.el_per_heat)/1000),
                        full_load_direct_MWh=float(np.sum(self.heat_max_kW*self.direct_fraction)/1000),
                        available_hours=int(np.count_nonzero(self.heat_max_kW>1e-8)),
                        potential_wp_air_hours=int(np.count_nonzero(wp_active & air)),
                        potential_wp_industry_hours=int(np.count_nonzero(wp_active & ~air)),
                        potential_wp_air_heating_MWh=float(np.sum(wp_heat[air])/1000.),
                        potential_wp_industry_heating_MWh=float(np.sum(wp_heat[~air])/1000.),
                        wp_industry_source_id=self.wp_industry_source_id if self.hx_areas_by_source_m2 else self.source_id,
                        included_sources=','.join(map(str,self.included_source_ids)),
                        excluded_sources=','.join(map(str,self.excluded_source_ids)),
                        hx_order_water=','.join(map(str,self.hx_order_water)),
                        strategy=self.strategy,
                        hx_area_by_source_m2=';'.join(f'{x:.6f}' for x in self.hx_areas_by_source_m2),
                        notes=self.notes)


    @dataclass
    class Input:
        source_kW: np.ndarray  # (sources, 8760) PFA: Waerme bis Tamb
        source_in_C: tuple
        q_codes: tuple
        ambient_C: np.ndarray
        return_C: np.ndarray
        supply_C: np.ndarray
        demand_kW: np.ndarray
        dual_enabled: bool
        hp_allowed: bool
        interest_rate: float
        hx_inv_eur_m2: dict = field(default_factory=lambda: th.HX_INV_EUR_M2_BY_CLASS)
        hx_om_eur_a: dict = field(default_factory=lambda: th.HX_OM_EUR_A_BY_CLASS)
        hx_lifetime_a: dict = field(default_factory=lambda: th.HX_LIFETIME_A_BY_CLASS)
        hx_annual_factor_by_class: dict | None = None
        def validate(self):
            q=np.asarray(self.source_kW,dtype=float)
            if q.ndim!=2 or q.shape[0]<1 or q.shape[1]<1:
                raise ValueError('DET: Quelle muss Matrix (S, Stunden) sein')
            n=q.shape[1]
            if len(self.source_in_C)!=q.shape[0] or len(self.q_codes)!=q.shape[0]:
                raise ValueError('DET: Anzahl Quelltemperaturen/-klassen stimmt nicht')
            for name in ('ambient_C','return_C','supply_C','demand_kW'):
                arr=np.asarray(getattr(self,name),dtype=float)
                if arr.shape!=(n,) or not np.isfinite(arr).all():
                    raise ValueError(f'DET: {name} muss {n} endliche Werte haben')
            if not np.isfinite(q).all() or (q<-1e-8).any():
                raise ValueError('DET: PFA-Profil enthaelt ungueltige Werte')
            if (np.asarray(self.demand_kW)<-1e-8).any():
                raise ValueError('DET: negative Nachfrage')
            # Einzelne Stillstandsstunden ohne Netz-Temperaturhub sind erlaubt.
            # Nur bei positiver Netznachfrage waere der Input physikalisch inkonsistent.
            supply=np.asarray(self.supply_C,dtype=float)
            ret=np.asarray(self.return_C,dtype=float)
            demand=np.asarray(self.demand_kW,dtype=float)
            no_lift=(supply<=ret)
            conflict=no_lift & (demand>1e-8)
            if np.any(conflict):
                t=int(np.flatnonzero(conflict)[0])
                raise ValueError(
                    f'DET: Positiver Netzbedarf ohne positiven Temperaturhub, Stunde {t}: '
                    f'T_supply={supply[t]:.3f} C, T_return={ret[t]:.3f} C, '
                    f'Bedarf={demand[t]:.6f} kW; '
                    f'insgesamt {int(np.count_nonzero(conflict))} betroffene Stunden. '
                    'Temperatur- und Nachfrageprofile pruefen; keine automatische Korrektur.'
                )
            if not isfinite(self.interest_rate) or self.interest_rate<0:
                raise ValueError('DET: ungueltiger Zinssatz')
            for c in self.q_codes:
                if c not in th.HX_U_W_M2K_BY_CLASS:
                    raise ValueError(f'DET: unbekannte Waermeuebertrager-Klasse {c}')


    def from_data(data, source_kW, demand_kW, interest_rate=0.05):
        """Quellen- und Netztemperaturen aus den echten WH1-Netzprofilen.

        WICHTIG: Diese Bruecke verwendet dieselben Klassen/Quellindizes wie
        heating_network_2leiter_industrie.load_industry(), nicht eine angenommene
        HX-Klasse aus dem Legacy-NPZ.
        """
        from districtgenerator.functions import heating_network_2leiter_industrie as net
        src=net.load_industry(data, 8760)
        codes=tuple(str(c).strip().upper() for c in src['source_info']['Quellklasse_Code'].tolist())
        inp=Input(source_kW=np.asarray(source_kW,dtype=float),
                  source_in_C=tuple(float(v) for v in src['temperatures_C']),
                  q_codes=codes, ambient_C=np.asarray(data.site['T_e'],dtype=float),
                  return_C=np.asarray(data.heat_grid_data['T_return_EH'],dtype=float),
                  supply_C=np.asarray(data.heat_grid_data['T_supply_EH'],dtype=float),
                  demand_kW=np.asarray(demand_kW,dtype=float),
                  dual_enabled=bool(data.heat_grid_data.get('industrial_dualsource_enabled',False)),
                  hp_allowed=(data.heat_grid_data.get('industrial_heat_mode')=='all_sources_hp'),
                  interest_rate=float(interest_rate))
        inp.validate()
        no_lift=(inp.supply_C<=inp.return_C)
        if np.any(no_lift):
            print(f'[WH1-DET] {int(np.count_nonzero(no_lift))} Stunden ohne positiven '
                  'Netztemperaturhub und ohne Netzbedarf: keine WH1-Einspeisung '
                  'in diesen Stunden (auch nicht durch Luft-WP).')
        from districtgenerator.functions import heating_network_2leiter as single_network
        inp.hx_annual_factor_by_class={q:float(single_network.calc_annual_factor(
            data,life)) for q,life in inp.hx_lifetime_a.items()}
        original=np.asarray(src['source_profiles_kW'],dtype=float)
        if original.shape != inp.source_kW.shape or not np.allclose(original,inp.source_kW,rtol=1e-8,atol=1e-6):
            raise ValueError('DET: Quellenprofil/-reihenfolge unterscheidet sich von der Netzwerkbruecke')
        return inp


    def annuity(interest, years):
        return 1.0/years if interest==0 else interest*(1+interest)**years/((1+interest)**years-1)


    def _mcp(inp, s, t):
        q=float(inp.source_kW[s,t]); diff=float(inp.source_in_C[s]-inp.ambient_C[t])
        return q/diff if q>1e-9 and diff>1e-6 else 0.0


    def _cop(out_C, supply_C):
        try:
            return th.hp_cop(out_C,supply_C)
        except ValueError:
            return 0.0


    def _air_cop(ambient_C, supply_C):
        # Die Kondensation benoetigt weiterhin >= Vorlauf, auch nach HX-Vorwaermung.
        return _cop(ambient_C, supply_C)


    def _best_wp_mode(industry_cop, air_cop):
        """Waehlt genau EINEN Verdampfermodus fuer EIN WP-Temperaturband.

        Rueckgabe ``(COP, luftbetrieb)`` oder ``None``. Die Kennwerte wurden
        zuvor fuer DENSELBEN Heizwasser-Austritt und DIESELBE WP-Heizleistung
        ermittelt. Industrie und Luft werden niemals gleichzeitig genutzt.

        Der industrielle Anschluss selbst wird hier nicht geaendert: Er ist
        bereits in der Anlagenvariante festgelegt. Bei Gleichstand wird
        reproduzierbar der Industrieverdampfer bevorzugt.
        """
        industry = 0.0 if industry_cop is None else float(industry_cop)
        air = 0.0 if air_cop is None else float(air_cop)
        if not (isfinite(industry) and isfinite(air)):
            raise ValueError('DET-WP: ungueltiger COP in der DualSource-Auswahl')
        if industry > 1.0 and (air <= 1.0 or industry >= air-1e-12):
            return industry, False
        if air > 1.0:
            return air, True
        return None


    def _hx_fraction(inp,s,t):
        tin=float(inp.source_in_C[s]); ret=float(inp.return_C[t]); sup=float(inp.supply_C[t])
        if sup<=ret:
            return 0.0
        # Bei Tin > Ts+5 kann auch die volle direkte Nutzung eine eigene Variante sein.
        mid=min(sup-0.1,tin-APPROACH_K)
        return max(0.,min(1.,(mid-ret)/(sup-ret))) if mid>ret+MIN_TEMPERATURE_RISE_K else 0.


    def _wp_evaporator_from_hot_stream(hot_in_C, ambient_C, supply_C, c_max_kW_K, q_wp_kW):
        """Zulaessiger WP-Verdampferpunkt fuer EINEN industriellen Quellstrom.

        Zunaechst wird der Vollstrom-Energiebilanzpunkt gesucht. Liegt dessen
        Quellenaustritt oberhalb der thermodynamisch zulaessigen Temperatur, wird
        nur ein Teil des Quellstroms durch den Verdampfer geleitet (Rest-Bypass).
        Der Industriestrom kann also nie groesser als der verfuegbare Vollstrom
        sein. Die feste WP-Anschlussquelle bleibt dadurch unveraendert.

        Rueckgabe (Quellenaustritt_C, COP, effektiver_Verdampfer-Cdot_kW_K)
        oder None, falls selbst bei voller Quelle nicht genug Verdampferenergie
        verfuegbar ist. NICHT durch COP <= 1 dividieren.
        """
        hot=float(hot_in_C); ambient=float(ambient_C); ts=float(supply_C)
        c=float(c_max_kW_K); q=float(q_wp_kW)
        if not all(isfinite(x) for x in (hot,ambient,ts,c,q)):
            return None
        if c<=0. or q<=0. or hot<=ambient+1e-9:
            return None
        cop_low=_cop(ambient,ts)
        if cop_low<=1.0:
            return None
        evap_low=q*(1.-1./cop_low)
        if c*(hot-ambient)+1e-7*max(1.,q)<evap_low:
            return None

        # Der Carnot-Hub muss POSITIV bleiben. Zusaetzlich waehlen wir
        # hoechstens den Austritt, bei dem die ungeklippte Kennlinie COP_MAX
        # erreicht; so wird nie nahe Carnot-Nullhub extrapoliert.
        tcond_K=ts+th.HP_COND_APPROACH_K+273.15
        max_thermo_out=ts+th.HP_COND_APPROACH_K+th.HP_EVAP_APPROACH_K-1e-5
        max_cop_out=(ts+th.HP_COND_APPROACH_K+th.HP_EVAP_APPROACH_K
                     -th.HP_ETA_CARNOT*tcond_K/th.HP_COP_MAX)
        high=min(hot,max_thermo_out,max(ambient,max_cop_out))
        if high<ambient-1e-8:
            return None
        cop_high=_cop(high,ts)
        if cop_high<=1.0:
            return None

        evap_high=q*(1.-1./cop_high)
        balance_high=c*(hot-high)-evap_high
        if balance_high>=0.:
            # Ein voller Quellstrom wuerde trotz maximal sinnvoller
            # Verdampferaustrittstemperatur zu WENIG abkuehlen. Statt
            # COP=0 oder unphysikalisch hoher T_evap: Quell-Teilstrom.
            cooling=hot-high
            if cooling<=1e-10:
                return None
            c_eff=evap_high/cooling
            if c_eff<=0. or c_eff>c+1e-7*max(1.,c):
                return None
            return (high,cop_high,min(c,c_eff))

        # Monotone Energiebilanz fuer unveraenderten vollen Quellstrom.
        lo=ambient; hi=high
        for _ in range(48):
            mid=0.5*(lo+hi)
            cop=_cop(mid,ts)
            if cop<=1.0:  # defensiv, auch bei spaeter geaenderter COP-Kennlinie
                hi=mid
                continue
            residual=c*(hot-mid)-q*(1.-1./cop)
            if residual>=0.:
                lo=mid
            else:
                hi=mid
        out=0.5*(lo+hi)
        cop=_cop(out,ts)
        if cop<=1.0:
            return None
        balance=c*(hot-out)-q*(1.-1./cop)
        if abs(balance)>1e-6*max(1.,q,c*(hot-ambient)):
            return None
        return (out,cop,c)


    def _wp_source_out_at_q(inp,s,t,q,frac_hx):
        """WP-Nutztemperatur nach dem optionalen direkten HX derselben Quelle.

        Der HX kann den ganzen sensiblen Quellstrom benutzen, die nachfolgende
        WP benoetigt bei kleiner Heizlast gegebenenfalls nur einen Teil davon.
        Das Medium bleibt dasselbe; es wird keine zweite WP-Quelle angeschlossen.
        """
        c=_mcp(inp,s,t)
        if c<=0 or q<=0:return None
        tin=float(inp.source_in_C[s]); amb=float(inp.ambient_C[t]); sup=float(inp.supply_C[t])
        qhx=q*frac_hx; qwp=q-qhx
        hot_after_hx=tin-qhx/c
        if hot_after_hx < amb-1e-8:
            return None
        if frac_hx>0 and hot_after_hx < float(inp.return_C[t])+APPROACH_K-1e-7:
            return None
        if qwp<1e-10:
            return (hot_after_hx,0.0)
        point=_wp_evaporator_from_hot_stream(hot_after_hx,amb,sup,c,qwp)
        if point is None:return None
        return (point[0],point[1])


    def _hx_area_at_q(inp,s,t,q_hx):
        if q_hx <= NUMERIC_EPS:return 0.
        c=_mcp(inp,s,t)
        if c<=0: return float('inf')
        tin=float(inp.source_in_C[s]); ret=float(inp.return_C[t]); sup=float(inp.supply_C[t])
        frac=_hx_fraction(inp,s,t)
        mid=ret+(sup-ret)*frac
        hotout=tin-q_hx/c
        st=th.hx_state(s,inp.q_codes[s],tin,hotout,ret,mid,APPROACH_K)
        return float('inf') if st is None else st.area_m2_per_kW*q_hx


    def _direct_possible(inp,s,t):
        return float(inp.source_in_C[s]) >= float(inp.supply_C[t])+APPROACH_K-1e-9


    def _technical_max(inp,s,t,family,peak_bound):
        # Bei Null-Netztemperaturhub gibt es keinen gueltigen Heizwasserweg.
        # Positiver Bedarf in solchen Stunden wurde bereits in validate() abgewiesen.
        if float(inp.supply_C[t])<=float(inp.return_C[t]):
            return 0.0
        c=_mcp(inp,s,t)
        if c<=0:return 0.
        tin=float(inp.source_in_C[s]);ret=float(inp.return_C[t]);amb=float(inp.ambient_C[t]);sup=float(inp.supply_C[t])
        max_source=max(0.,c*(tin-max(amb,ret+APPROACH_K)))
        if family=='hx_only':
            return max_source if _direct_possible(inp,s,t) else 0.
        frac=0. if family=='industry_wp' else _hx_fraction(inp,s,t)
        if family=='industry_wp':
            cop=_cop(amb,sup)
            return max(0.,c*(tin-amb)/(1-1/cop)) if cop>1 else 0.
        if frac<=1e-9 or frac>=1.-1e-9:return 0.
        if family=='hx_air_wp':
            return min(peak_bound,max_source/frac)
        if family=='hx_rest_wp':
            # Extremfall: Quellenende = Tamb, COP wird fuer diesen Grenzzustand
            # eingesetzt; fuer kleinere Leistungen wird Tout > Tamb und COP besser.
            cop=_cop(amb,sup)
            if cop<=1:return 0.
            source_per_heat=frac+(1-frac)*(1-1/cop)
            return min(peak_bound,c*(tin-amb)/source_per_heat,max_source/frac)
        raise ValueError(f'Unbekannte Familie {family}')


    def _make(inp,s,family,factor,technical=None):
        n=inp.source_kW.shape[1]
        h=np.zeros(n); e=np.zeros(n); f=np.zeros(n); air_share=np.zeros(n)
        demand=np.asarray(inp.demand_kW,dtype=float)
        peak_bound=max(1.,float(demand.max())*1.25)
        if technical is None:
            technical=np.array([_technical_max(inp,s,t,family,peak_bound) for t in range(n)])
        target=np.minimum(technical,factor*demand)
        k=float(target.max())
        if k <=1e-6:return None
        # Kein aufgezwungener 70/90/110%-Deckel im Stundenbetrieb:
        # volle installierte Leistung kann fuer TES-Ladung benutzt werden.
        rated=np.minimum(k,technical)
        hx_areas=[]
        for t,q in enumerate(rated):
            if q<=0:continue
            if family=='hx_only':
                c=_mcp(inp,s,t)
                hotout=float(inp.source_in_C[s])-q/c
                st=th.hx_state(s,inp.q_codes[s],inp.source_in_C[s],hotout,
                               inp.return_C[t],inp.supply_C[t],APPROACH_K)
                hx_areas.append(float('inf') if st is None else q*st.area_m2_per_kW)
            elif family.startswith('hx_'):
                hx_areas.append(_hx_area_at_q(inp,s,t,q*_hx_fraction(inp,s,t)))
        area=max(hx_areas,default=0.0)
        if not isfinite(area) or area<0:
            raise ValueError(f'DET: HX-Flaeche nicht berechenbar fuer Quelle {s} und {family}')
        wp_peak=0.
        for t,q in enumerate(rated):
            if q<=1e-8:continue
            if family=='hx_only':
                f[t]=1.
            elif family=='industry_wp':
                # Eine feste Industriequelle, bei DualSource stundenweise
                # der guenstigere ZULAESSIGE Verdampferbetrieb (Industrie/Luft).
                state=_wp_source_out_at_q(inp,s,t,q,0.)
                aircop=_air_cop(inp.ambient_C[t],inp.supply_C[t]) if inp.dual_enabled else 0.
                selected=_best_wp_mode(state[1] if state is not None else None,aircop)
                if selected is None:
                    raise ValueError('DET: Industrie-/DualSource-WP-Auslegung nicht reproduzierbar')
                cop,use_air=selected
                f[t]=0.
                e[t]=1./cop
                air_share[t]=float(use_air)
                wp_peak=max(wp_peak,q)
            else:
                frac=_hx_fraction(inp,s,t)
                f[t]=frac
                # AUCH die bisherige Familie hx_air_wp besitzt bei
                # DualSource denselben festen Industrieanschluss. 'air' im
                # Familiennamen bezeichnet weiterhin ihre HX-/WP-SCREENING-
                # Auslegungsregel, NICHT mehr einen erzwungenen Luftbetrieb.
                # Beide Kategorien vergleichen den realen Restwaerme-COP
                # mit dem Luft-COP fuer denselben oberen Heizwasser-Resthub.
                state=_wp_source_out_at_q(inp,s,t,q,frac)
                aircop=_air_cop(inp.ambient_C[t],inp.supply_C[t]) if inp.dual_enabled else 0.
                selected=_best_wp_mode(state[1] if state is not None else None,aircop)
                if selected is None:
                    raise ValueError('DET: weder Industrie- noch Luft-WP-Betriebspunkt zulaessig')
                cop,use_air=selected
                e[t]=(1-frac)/cop
                air_share[t]=float(use_air)
                wp_peak=max(wp_peak,q*(1-frac))
            h[t]=q
        # Luft-WP darf auch waehrend Industrie-Stillstand heizen, aber nur mit
        # der ohnehin installierten (kostenpflichtigen) WP-Kapazitaet.
        if inp.dual_enabled and wp_peak>1e-8 and ALLOW_AIR_ONLY_WITH_DUALSOURCE:
            off=(np.asarray(inp.source_kW[s])<=1e-9) | (technical<=1e-9)
            for t in np.flatnonzero(off):
                # Nicht mit einer Luft-WP in Stunden ohne Netztemperaturhub heizen.
                if float(inp.supply_C[t])<=float(inp.return_C[t]):
                    continue
                cop=_air_cop(inp.ambient_C[t],inp.supply_C[t])
                if cop>1 and wp_peak>0:
                    h[t]=min(k,wp_peak)
                    f[t]=0.
                    e[t]=1./cop
                    air_share[t]=1.
        qcode=inp.q_codes[s]
        inv=float(area*inp.hx_inv_eur_m2[qcode])
        om=float(inp.hx_om_eur_a[qcode]) if area>1e-7 else 0.
        ann_factor=(inp.hx_annual_factor_by_class[qcode]
                    if inp.hx_annual_factor_by_class is not None
                    else annuity(inp.interest_rate,int(inp.hx_lifetime_a[qcode])))
        annual=float(inv*ann_factor+om)
        wp_kind='none' if wp_peak<1e-8 else ('dual' if inp.dual_enabled else 'normal')
        label=f'S{s}_{family}_{int(round(factor*100))}'
        wp_note=('keine WP' if wp_kind=='none' else
                 ('DualSource: stundenweise hoeherer zulaessiger COP, '
                  'fester Industrieanschluss' if wp_kind=='dual' else
                  'normale Industrie-WP'))
        return Variant(label,family,s,float(factor),k,area,wp_peak,wp_kind,
                       annual,inv,om,h,e,f,
                       notes=('1h; fester nominaler Temperaturzustand je Stunde; '
                              'proportionale Teillast; '+wp_note),
                       air_share=air_share)


    # Echte Registry: neue Kategorie in eigenem Modul registrieren; EHDO bleibt gleich.
    REGISTRY: dict[str,Callable[[Input],list[Variant]]] = {}


    def register(name):
        def decorator(func):
            if name in REGISTRY:raise ValueError('DET: Variantenfamilie doppelt registriert')
            REGISTRY[name]=func
            return func
        return decorator


    @register('single_source')
    def generate_single_sources(inp):
        families=['hx_only']
        if inp.hp_allowed:
            families+=['industry_wp','hx_rest_wp']
            if inp.dual_enabled:families+=['hx_air_wp']
        variants=[]
        for s in range(inp.source_kW.shape[0]):
            for family in families:
                bound=max(1.,float(np.max(inp.demand_kW))*1.25)
                technical=np.array([_technical_max(inp,s,t,family,bound) for t in range(inp.source_kW.shape[1])])
                if not np.any(technical>1e-6):continue
                for factor in SIZE_FACTORS:
                    v=_make(inp,s,family,factor,technical=technical)
                    if v is not None: variants.append(v)
        return variants


    def generate(inp,categories=('single_source',),include_baseline=True,*,return_deduplication=False):
        inp.validate()
        result=[]
        if include_baseline:
            n=inp.source_kW.shape[1]
            result.append(Variant('V0_ohne_WH1','baseline',-1,0,0,0,0,'none',0,0,0,
                                  np.zeros(n),np.zeros(n),np.zeros(n)))
        for category in categories:
            if category == 'multi_source_cascade' and category not in REGISTRY:
                # Nur bei Bedarf laden; keine Advanced-Abhaengigkeit.
                industrie_deterministisch_mehrquellen = _mehrquellen  # noqa:F401
            if category not in REGISTRY:
                raise KeyError(f'DET: Variantenkategorie {category} nicht registriert')
            result.extend(REGISTRY[category](inp))
        # Kategorienuebergreifend: gleiche physische Anlage + dieselben
        # Stundenprofile und Kosten, nicht nur identische Rundungs-Hashes.
        dedupe = _dubletten
        unique, aliases = dedupe.deduplicate(result, inp.source_kW.shape[0])
        if return_deduplication:
            return unique, aliases
        return unique


    def monthly_plateau_audit(source_profiles):
        """Nur Diagnose. Vorhandene PFA-Profile niemals stillschweigend aendern."""
        import calendar
        a=np.asarray(source_profiles,dtype=float)
        if a.ndim!=2 or a.shape[1]!=8760:return []
        issues=[]; start=0
        for m in range(1,13):
            end=start+calendar.monthrange(2025,m)[1]*24
            for s in range(a.shape[0]):
                active=a[s,start:end][a[s,start:end]>1e-9]
                if active.size and np.ptp(active)>max(0.01,1e-4*np.max(active)):
                    issues.append((s,m,float(np.min(active)),float(np.max(active))))
            start=end
        return issues
    return _DetNamespace(**locals())
_varianten = _init_varianten()
del _init_varianten

# ===========================================================================
# Originalbaustein: industrie_deterministisch_mehrquellen.py
# ===========================================================================
def _init_mehrquellen():
    # -*- coding: utf-8 -*-
    """WH1 Kategorie 2: deterministische Mehrquellen-HX-Kaskade + hoechstens eine WP.

    Rechenprinzip:
    * Statische Quell-Prioritaet: Tin absteigend, bei Gleichstand Jahres-PFA absteigend.
    * Ausschlusspraefixe, solange MIN_REMAINING_SOURCES Quellen verbleiben.
    * Zuordnung der HX-Temperaturbaender RECHNERISCH RUECKWAERTS vom
      hoechsten direkt erreichbaren Temperaturniveau zur Ruecklauftemperatur.
      Physische Wasserreihenfolge ist die dazu umgekehrte (kalt -> heiss).
    * Eine nachgeschaltete WP deckt genau EINEN zusammenhaengenden Resthub.
    * Je Anlagenvariante exakt EINE fest zugeordnete industrielle WP-Quelle;
      DualSource darf alternativ Luft einsetzen, NIEMALS beide simultan.
    * Kein WP-Quellenwechsel zwischen Industriequellen waehrend des Betriebs.
    * Industriequelle nach HX muss fuer den Verdampfer mit ihrer wirklichen
      verbleibenden Temperatur und Waermemenge gerechnet werden.
    * Der direkte Vorrang bleibt absichtlich eine Heuristik. Eine separate
      reservierte WP-Quelle ist KEIN automatischer zweiter Greedy-Pfad.

    Abhaengigkeiten nur zum unabhaengigen Deterministik-Physik-/Variantencode.
    Keine Imports aus industrie_advanced_* .
    """
    from dataclasses import dataclass
    from math import isfinite
    import numpy as np
    th = _physik
    base = _varianten

    MIN_REMAINING_SOURCES = 2
    BINARY_SEARCH_STEPS = 32
    TOL = 1e-7


    @dataclass
    class Point:
        """Vollstaendig feste thermische Stunde (keine Pyomo-Zustandswahl)."""
        q_total: float
        q_direct: np.ndarray
        q_wp: float
        p_wp: float
        air: bool
        wp_source: int
        hx_area: np.ndarray
        source_after_hx_C: np.ndarray
        water_after_hx_C: float


    def source_priority(inp):
        """Ganzjaehrig FESTE Reihenfolge; kein stundenweises Umordnen der HX."""
        energy = np.asarray(inp.source_kW).sum(axis=1)
        return tuple(sorted(range(inp.source_kW.shape[0]),
                            key=lambda s: (-float(inp.source_in_C[s]), -float(energy[s]), s)))


    def exclusion_sets(inp):
        """Nur n,n-1,...,2 Quellen. Einzelfaelle kommen aus single_source."""
        priority=source_priority(inp)
        for count in range(max(0,len(priority)-MIN_REMAINING_SOURCES+1)):
            yield count, priority[:count], priority[count:]


    def _direct_backward(inp, included, t, q_total):
        """HX-Baender von oben nach unten vergeben, gemeinsamer Wasser-Cdot.

        Bei vorgegebenem Gesamtwaermestrom Q_total gilt Cw=Q_total/(Ts-Tr).
        Hoechste direkt erreichbare Wasseraustrittstemperatur ist Tin_max-5K.
        Ein naechster HX mit zu geringer Tin kann kein hohes Band uebernehmen;
        sein moeglicher Beitrag wird erst unterhalb des bereits vergebenen
        Temperaturbandes zugeordnet. Beide Gegenstrom-Enden werden geprueft.
        """
        S=inp.source_kW.shape[0]
        direct=np.zeros(S,dtype=float)
        areas=np.zeros(S,dtype=float)
        outlets=np.asarray(inp.source_in_C,dtype=float).copy()
        tr=float(inp.return_C[t]); ts=float(inp.supply_C[t])
        if q_total<=TOL:
            return direct,areas,outlets,tr
        cw=q_total/(ts-tr)
        valid=[s for s in included if base._mcp(inp,s,t)>TOL and
               float(inp.source_in_C[s])>tr+base.APPROACH_K+TOL]
        if not valid:
            return direct,areas,outlets,tr
        # Zunaechst das ohne Zwischen-WP wirklich ERREICHBARE obere Niveau
        # ermitteln: physisch fliesst das Wasser von kalt nach heiss. Ein
        # reiner Rueckwaertsstart bei 71C kann sonst eine NICHT auffuellbare
        # Luecke zwischen den HX-Temperaturbaendern erzeugen.
        forward=tr
        for s in reversed(included):
            cs=base._mcp(inp,s,t)
            tin=float(inp.source_in_C[s]);amb=float(inp.ambient_C[t])
            head=tin-base.APPROACH_K-forward
            if cs<=TOL or head<=TOL or forward>=ts-TOL:
                continue
            d=min(ts-forward,head,head*cs/cw,cs*(tin-amb)/cw)
            if d>TOL:
                forward+=d
        # Erst DANACH werden die Baender rueckwaerts zugeordnet:
        # hoechste Quelle bekommt oberstes DIREKT erreichbares Band.
        target=min(forward,ts)
        for s in included:  # bereits nach absteigendem Tin/Jahres-PFA sortiert
            if target<=tr+TOL:
                break
            cs=base._mcp(inp,s,t)
            tin=float(inp.source_in_C[s]); amb=float(inp.ambient_C[t])
            if cs<=TOL or tin<target+base.APPROACH_K-TOL:
                continue
            delta=target-tr
            # Source cooling to ambient, mass/energy conservation
            delta=min(delta,cs*(tin-amb)/cw)
            # Gegenstrom-Pinch am kalten Ende: Tout_source - Twin_water >= 5 K
            ratio=cw/cs
            if ratio>1.0+1e-11:
                delta=min(delta,max(0.,(tin-target-base.APPROACH_K)/(ratio-1.)))
            delta=max(0.,delta)
            if delta<=TOL:
                continue
            water_in=target-delta
            qhx=cw*delta
            hotout=tin-qhx/cs
            state=th.hx_state(s,inp.q_codes[s],tin,hotout,water_in,target,base.APPROACH_K)
            if state is None:
                # Rein numerische Randbedingungen tolerieren wir nicht stillschweigend.
                # Ein kleinerer Abstand wird durch minimal konservative Reduktion erreicht.
                qhx *= (1-1e-8)
                water_in=target-qhx/cw
                hotout=tin-qhx/cs
                state=th.hx_state(s,inp.q_codes[s],tin,hotout,water_in,target,base.APPROACH_K)
                if state is None:
                    raise ValueError(f'DET-MULTI: HX {s} erfuellt nicht beide Pinch-Enden')
            direct[s]=qhx
            outlets[s]=hotout
            areas[s]=qhx*state.area_m2_per_kW
            target=water_in
        water_after=tr+float(direct.sum())/cw
        # Die physische Wasserfolge ist genau die umgekehrte Rueckwaerts-Zuordnung.
        return direct,areas,outlets,water_after


    def _industry_hp_state(inp,wp_source,t,tin_evap_in,q_wp):
        """WP mit EINER festen Industriequelle nach deren direktem HX.

        Die physikalisch zulaessige Verdampfer-Teilstromregel wird mit der
        Einzelquellenkategorie geteilt: keine Division durch COP=0, keine
        zweite Industriequelle und kein unmoeglicher negativer Carnot-Hub.
        Gibt (COP,source_out) oder None zurueck.
        """
        if wp_source<0 or q_wp<=TOL:
            return None
        cs=base._mcp(inp,wp_source,t)
        amb=float(inp.ambient_C[t]);ts=float(inp.supply_C[t])
        if cs<=TOL or tin_evap_in<=amb+TOL:
            return None
        state=base._wp_evaporator_from_hot_stream(tin_evap_in,amb,ts,cs,q_wp)
        if state is None:
            return None
        return (state[1],state[0])


    def point(inp,included,t,q_total,wp_source=-1,*,allow_air=False):
        """Berechnet genau EINEN Betriebspunkt, keine Kombination von WP-Quellen.

        Luft wird nur bei freigegebener DualSource verwendet. Bei beiden
        technisch moeglichen Verdampfern wird derjenige mit geringerem
        Strombedarf / hoeherem COP verwendet (kein stundenweiser
        INDUSTRIEQUELLENWECHSEL!).
        """
        S=inp.source_kW.shape[0]
        if q_total<=TOL:
            return Point(0.,np.zeros(S),0.,0.,False,wp_source,np.zeros(S),
                         np.asarray(inp.source_in_C,dtype=float).copy(),float(inp.return_C[t]))
        if float(inp.supply_C[t])<=float(inp.return_C[t]):
            # Keine positive WH1-Erzeugung ohne gueltiges Netzerwaermungsband.
            return None
        direct,areas,outlets,water_after=_direct_backward(inp,included,t,q_total)
        qhx=float(direct.sum())
        qwp=max(0.,float(q_total)-qhx)
        if qwp<=TOL:
            return Point(q_total,direct,0.,0.,False,wp_source,areas,outlets,water_after)
        # WP im einzigen Resttemperaturband (Wasser nach HX -> Netzvorlauf).
        # COP der bisherigen Deterministik verwendet Kondensator-Austritt Ts.
        ind=None
        if wp_source>=0 and wp_source in included:
            ind=_industry_hp_state(inp,wp_source,t,float(outlets[wp_source]),qwp)
        aircop=base._air_cop(inp.ambient_C[t],inp.supply_C[t]) if allow_air else 0.
        # Dieselbe Regel wie in single_source, aber mit dem festen
        # Mehrquellen-Verdampferanschluss. Nie mehrere Industriequellen
        # gleichzeitig und nie zwei WP-Temperaturbaender.
        selected=base._best_wp_mode(ind[0] if ind is not None else None,aircop)
        if selected is None:
            return None
        cop,use_air=selected
        return Point(q_total,direct,qwp,qwp/cop,use_air,wp_source,areas,outlets,water_after)


    def _technical_max(inp,included,t,wp_source,allow_air,peak_bound):
        if float(inp.supply_C[t])<=float(inp.return_C[t]):
            return 0.0
        # Mit Luft kann die einzige WP im erlaubten Temperaturband bis zur
        # betrachteten Screening-Obergrenze liefern; die Endauslegung wird
        # anschliessend auf eine feste WP-Kapazitaet und HX-Flaechen geprueft.
        if allow_air and base._air_cop(inp.ambient_C[t],inp.supply_C[t])>1:
            return peak_bound
        # Ohne Luft: Quelle(n) und ein fester Industrieverdampfer bestimmen Qmax.
        # Bei sehr kleinem Wasserstrom laesst sich der gesamte Hub evtl. direkt
        # bereitstellen, auch wenn fuer groessere Q eine WP erforderlich ist.
        lo,hi=0.,peak_bound
        for _ in range(BINARY_SEARCH_STEPS):
            mid=(lo+hi)/2
            if point(inp,included,t,mid,wp_source,allow_air=False) is not None:lo=mid
            else:hi=mid
        return lo if lo>1e-5 else 0.


    def _direct_linked_reference_max(inp, included, t, peak_bound):
        """Auslegungs-Referenz aus industriell angebotener DIREKTer Waerme.

        Anders als eine freie Luft-WP kann ein Mehrquellen-HX+WP-Kandidat
        seine Auslegungsleistung nicht allein aus dem Quartiers-Spitzenbedarf
        ableiten. Jede noch fuer Direktwaerme geeignete Quelle liefert einen
        HX-bezogenen technischen Referenzwert aus derselben Regel, die auch
        die bisherige Einzelquelle 'hx_air_wp' verwendet.

        Ueber mehrere Quellen werden diese Werte konservativ als
        *Screening-Obergrenze* addiert; der tatsaechliche Betriebspunkt und
        die HX-Pinch-/Quellenbilanzen werden weiterhin von point() geprueft.
        Das ist eine HEURISTIK fuer die Anlagenwahl, keine optimale
        thermodynamische Auslegung.
        """
        if float(inp.supply_C[t]) <= float(inp.return_C[t]):
            return 0.0
        return min(float(peak_bound), sum(
            base._technical_max(inp, s, t, 'hx_air_wp', peak_bound)
            for s in included
        ))


    def _make(inp,idx,excluded,included,factor,wp_source,technical):
        S,n=inp.source_kW.shape
        k=float(np.max(np.minimum(technical,factor*np.asarray(inp.demand_kW))))
        if k<=TOL:
            return None
        heat=np.zeros(n);el=np.zeros(n);f=np.zeros(n);air=np.zeros(n)
        ds=np.zeros((S,n)); area=np.zeros(S)
        wppeak=0.
        qdirect_year=0.; qindustrial_wp_year=0.
        for t in range(n):
            q=min(float(technical[t]),k)
            if q<=TOL:
                continue
            state=point(inp,included,t,q,wp_source,allow_air=inp.dual_enabled)
            if state is None:
                raise ValueError(f'DET-MULTI: technisch positive Leistung unzulaessig, Stunde {t}')
            heat[t]=q
            ds[:,t]=state.q_direct/q
            f[t]=float(state.q_direct.sum())/q
            area=np.maximum(area,state.hx_area)
            el[t]=state.p_wp/q
            air[t]=float(state.air and state.q_wp>1e-8)
            wppeak=max(wppeak,state.q_wp)
            qdirect_year+=float(state.q_direct.sum())
            if state.q_wp>TOL and not state.air:
                qindustrial_wp_year+=state.q_wp
        # Gleiches DualSource-Designprinzip wie in der EINZELQUELLEN-Kategorie:
        # Bei ausfallender/nicht direkt nutzbarer Industrie bleibt die bereits
        # installierte WP als Luft-WP nutzbar, aber nur bis zur WP-Nennleistung.
        # Diese Ersatzstunden duerfen die WP nicht nachtraeglich groesser machen.
        if inp.dual_enabled and wppeak > TOL:
            for t in np.flatnonzero(technical <= TOL):
                if float(inp.supply_C[t]) <= float(inp.return_C[t]):
                    continue
                cop=base._air_cop(inp.ambient_C[t],inp.supply_C[t])
                if cop <= 1.0:
                    continue
                q=min(k,wppeak)
                heat[t]=q
                el[t]=1.0/cop
                f[t]=0.0
                air[t]=1.0

        # Keine durch HX oder Industrie-Restwaerme begruendete Mehrquellenanlage:
        # Ein reines Luft-WP-Duplikat ist keine neue Mehrquellen-Kaskade.
        if qdirect_year<=1e-6:
            return None
        # Eine angeblich fest angeschlossene Industriequelle, die nie als
        # Verdampfer dient, hat keinen eigenen technischen Nutzen. Der air-only
        # Kandidat (ohne Industrieanschluss) bildet dieses Profil bereits ab.
        if wp_source>=0 and wppeak>TOL and qindustrial_wp_year<=1e-6:
            return None
        if wppeak<=1e-7 and wp_source>=0:
            # Fuer reine Direktanlage nur EIN technischer Kandidat.
            return None
        inv=np.zeros(S);om=np.zeros(S);ann=np.zeros(S)
        for s in range(S):
            if area[s]>1e-9:
                qcode=inp.q_codes[s]
                inv[s]=area[s]*inp.hx_inv_eur_m2[qcode]
                om[s]=inp.hx_om_eur_a[qcode]
                ann_factor=(inp.hx_annual_factor_by_class[qcode]
                            if inp.hx_annual_factor_by_class is not None
                            else base.annuity(inp.interest_rate,int(inp.hx_lifetime_a[qcode])))
                ann[s]=inv[s]*ann_factor+om[s]
        if wppeak<=TOL:kind='none'
        else:kind='dual' if inp.dual_enabled else 'normal'
        source=-1 if kind=='none' else wp_source
        name=(f'MC_ex{idx}_'+('direct' if kind=='none' else
              ('air' if wp_source<0 else f'wpS{wp_source}'))+
              f'_{int(round(factor*100))}')
        return base.Variant(
            id=name,family='multi_source_cascade',source_id=source,factor=float(factor),
            heat_cap_kW=k,hx_area_m2=float(area.sum()),wp_cap_kW=wppeak,
            wp_kind=kind,annual_hx_cost_EUR_a=float(ann.sum()),
            hx_investment_EUR=float(inv.sum()),hx_om_EUR_a=float(om.sum()),
            heat_max_kW=heat,el_per_heat=el,direct_fraction=f,
            air_share=air,
            notes=('Kaskade: heisseste Quelle hoechstes Temperaturband; '
                   'eine WP am Ende; feste Industrie-Anschlussquelle; '
                   'linear proportionale Teillast'),
            hx_areas_by_source_m2=tuple(area),
            hx_investment_by_source_EUR=tuple(inv),
            hx_om_by_source_EUR_a=tuple(om),
            hx_annual_by_source_EUR_a=tuple(ann),
            direct_fraction_by_source=ds,wp_industry_source_id=source,
            included_source_ids=tuple(included),excluded_source_ids=tuple(excluded),
            hx_order_water=tuple(reversed(included)),strategy='direct_first')


    @base.register('multi_source_cascade')
    def generate_multi_source(inp):
        """O(n^2) feste Anschlussalternativen statt 2^n Untergruppen.

        Fuer jede Ausschlussstufe und jeden moeglichen Industrieanschluss wird
        ein gesamtes Jahresprofil gewaehlt. Das ist die robuste Umsetzung
        'besten COP pruefen' bei gleichzeitig fester WP-Anschlussquelle:
        es wird KEIN Quellwechsel innerhalb einer Variante modelliert;
        die wirtschaftliche Auswahl erfolgt spaeter ueber alle EHDO-TAC.
        """
        if inp.source_kW.shape[0]<MIN_REMAINING_SOURCES:return []
        n=inp.source_kW.shape[1]
        peak_bound=max(1.,float(np.max(inp.demand_kW))*1.25)
        variants=[]
        for idx,excluded,included in exclusion_sets(inp):
            # Direkte HX-only-Variante auch dann, wenn die Anlagentemperaturen
            # die vollen 71C nur teilweise erreichen; falls WP erforderlich, ist
            # diese reine HX-Variante technisch nicht fuer WH1-Netzeinspeisung geeignet.
            # Der Quellanschluss ist ein Designmerkmal. Fuer Normal-WP jede
            # verbliebene Quelle, fuer DualSource zusaetzlich rein Luft als Kandidat.
            choices=[-1] if not inp.hp_allowed else list(included)+([-1] if inp.dual_enabled else [])
            if not choices:
                continue
            # Einen direkten Nur-HX-Kandidaten unabhaengig von WP-Zulassung pruefen.
            direct_technical=np.zeros(n)
            for t in range(n):
                lo,hi=0.,peak_bound
                for _ in range(BINARY_SEARCH_STEPS):
                    mid=(lo+hi)/2
                    state=point(inp,included,t,mid,wp_source=-1,allow_air=False)
                    if state is not None:lo=mid
                    else:hi=mid
                direct_technical[t]=lo if lo>1e-5 else 0.
            for factor in base.SIZE_FACTORS:
                v=_make(inp,idx,excluded,included,factor,-1,direct_technical)
                if v is not None: variants.append(v)
            if not inp.hp_allowed:continue
            # Industriegebundene Screening-Huelle NUR aus Stunden/Quellen mit
            # technisch moeglicher direkter Industrie-Vorwaermung. Die DualSource-
            # Luftreserve darf nicht aus dem vollen Quartiers-Spitzenbedarf
            # heraus eine unbezahlt viel groessere WP-Nennleistung erzwingen.
            # Bei Industrie-Stillstand wird die spaetere Luftreserve in _make()
            # auf die bereits festgelegte WP-Nennleistung begrenzt.
            linked=np.array([_direct_linked_reference_max(inp,included,t,peak_bound)
                             for t in range(n)])
            for fixed_source in choices:
                if fixed_source<0 and not inp.dual_enabled:continue
                if fixed_source>=0 and not np.any(inp.source_kW[fixed_source]>1e-9):
                    continue
                thermal_limit=np.array([_technical_max(inp,included,t,fixed_source,
                               inp.dual_enabled,peak_bound) for t in range(n)])
                technical=np.minimum(linked,thermal_limit)
                for factor in base.SIZE_FACTORS:
                    v=_make(inp,idx,excluded,included,factor,fixed_source,technical)
                    if v is not None: variants.append(v)
        return variants
    return _DetNamespace(**locals())
_mehrquellen = _init_mehrquellen()
del _init_mehrquellen

# ===========================================================================
# Originalbaustein: industrie_deterministisch_dubletten.py
# ===========================================================================
def _init_dubletten():
    # -*- coding: utf-8 -*-
    """Konservative, kategorienuebergreifende Dublettenerkennung fuer WH1-DET.

    Verglichen wird die tatsaechlich in EHDO genutzte physische Anlage samt
    8760-Stunden-Parametern, nicht die Kategorie, der Name oder nur Jahresenergien.
    Jede tolerante Gleichheit wird DIREKT mit einem behaltenen Repraesentanten
    geprueft (keine nichttransitiven Ketten A~B~C). Nie Hash-Rundungen als Beweis.

    Neue in EHDO kosten- oder physikrelevante Variant-Felder muessen in
    _make_view() aufgenommen werden, BEVOR eine neue Variante produktiv geht.
    """

    from dataclasses import dataclass
    import numpy as np

    # V4: Enge lokale Grenzen UND explizites Jahres-Abweichungsbudget.
    # Begruendung: Die thermischen Einzel- und Mehrquellenroutinen verwenden
    # unterschiedliche Bisection-/Pinch-Rechenwege. Bei G20 fuehrte das zu
    # Unterschieden von ca. 0.000000088 m2, 0.00011 EUR Investition und
    # 0.29 kWh/a Waermepotenzial, obwohl beide Anlagen technisch dieselben sind.
    # Keine relative np.allclose-Toleranz: grosse Nennleistungen duerfen nicht
    # zu grossen absoluten Abweichungen fuehren.
    #
    # ACHTUNG: PROFILE_ABS_BUDGET_KWH setzt einstündige Zeitpunkte voraus.
    # Die WH1-DET-Eingabe enthaelt die 8760 einzelnen Kalenderstunden.
    HEAT_ATOL_KW = 1e-4
    EFFECTIVE_HEAT_ATOL_KW = 1e-4
    PROFILE_ABS_BUDGET_KWH = 0.75
    CAPACITY_ATOL_KW = 1e-4
    AREA_ATOL_M2 = 1e-6
    # Ein winziger HX bleibt strukturell ein HX, auch wenn seine Flaechendifferenz
    # mit einem anderen Kandidaten unter der numerischen Flaechentoleranz liegt.
    INSTALLED_HX_THRESHOLD_M2 = 1e-9
    INVESTMENT_ATOL_EUR = 1e-3
    ANNUAL_COST_ATOL_EUR_A = 1e-4
    OM_ATOL_EUR_A = 1e-5
    FRACTION_ATOL = 1e-6
    EL_PER_HEAT_ATOL = 1e-7


    @dataclass(frozen=True)
    class _View:
        variant: object
        kind: str
        wp_source: int
        hx_order: tuple[int, ...]
        heat_cap: float
        wp_cap: float
        total_area: float
        total_investment: float
        total_om: float
        total_annual: float
        heat: np.ndarray
        el_per_heat: np.ndarray
        direct: np.ndarray
        air: np.ndarray
        direct_sources: np.ndarray
        areas: np.ndarray
        investments: np.ndarray
        om: np.ndarray
        annual: np.ndarray

        @property
        def group(self):
            # Keine gerundeten floats in der Vorauswahl: andernfalls entstehen
            # falsche NICHT-Dubletten an Rundungsgrenzen.
            return (self.kind, self.wp_source, self.hx_order,
                    self.heat.shape, self.direct_sources.shape,
                    tuple(np.flatnonzero(self.areas > INSTALLED_HX_THRESHOLD_M2)),
                    int(np.count_nonzero(self.air > 0.5)))


    def _array(value, name, shape=None):
        arr = np.asarray(value, dtype=np.float64)
        if shape is not None and arr.shape != shape:
            raise ValueError(f'WH1-DET Dubletten: {name} hat Form {arr.shape}, erwartet {shape}')
        if not np.isfinite(arr).all():
            raise ValueError(f'WH1-DET Dubletten: {name} enthaelt NaN/Inf')
        return arr


    def _make_view(v, sources):
        heat = _array(v.heat_max_kW, 'heat_max_kW')
        if heat.ndim != 1:
            raise ValueError('WH1-DET Dubletten: Waermeprofil muss eindimensional sein')
        n = heat.size
        area, inv, om, annual, source_direct = v.per_source_arrays(sources)
        area = _array(area, 'HX-Flaeche', (sources,))
        inv = _array(inv, 'HX-Investition', (sources,))
        om = _array(om, 'HX-OM', (sources,))
        annual = _array(annual, 'HX-Jahreskosten', (sources,))
        source_direct = _array(source_direct, 'Direktanteil je Quelle', (sources, n))
        air = (_array(v.air_share, 'Luftmodus', (n,)) if len(v.air_share)
               else np.zeros(n, dtype=float))
        if np.any((air != 0.) & (air != 1.)):
            raise ValueError('WH1-DET Dubletten: Luftmodus muss binaer sein')
        scalars = (v.heat_cap_kW, v.wp_cap_kW, v.hx_area_m2,
                   v.hx_investment_EUR, v.hx_om_EUR_a, v.annual_hx_cost_EUR_a)
        if not np.isfinite(np.asarray(scalars, dtype=float)).all():
            raise ValueError(f'WH1-DET Dubletten: ungueltige Anlagenskalarwerte bei {v.id}')
        wp_source = (int(v.wp_industry_source_id)
                     if v.hx_areas_by_source_m2 else int(v.source_id))
        if v.wp_kind == 'none':
            wp_source = -1  # Ein HX ohne WP hat keinen Verdampferanschluss.
        # Die Reihenfolge ist nur fuer tatsaechlich installierte HX relevant.
        installed = tuple(int(s) for s in np.flatnonzero(area > INSTALLED_HX_THRESHOLD_M2))
        if v.hx_order_water:
            order = tuple(s for s in v.hx_order_water if s in installed)
            if set(order) != set(installed) or len(order) != len(installed):
                raise ValueError(f'WH1-DET Dubletten: unvollstaendige HX-Reihenfolge bei {v.id}')
        else:
            if len(installed) > 1:
                raise ValueError('WH1-DET Dubletten: fehlende Reihenfolge mehrerer HX')
            order = installed
        return _View(
            variant=v, kind=str(v.wp_kind), wp_source=wp_source,
            hx_order=order, heat_cap=float(v.heat_cap_kW),
            wp_cap=float(v.wp_cap_kW), total_area=float(v.hx_area_m2),
            total_investment=float(v.hx_investment_EUR),
            total_om=float(v.hx_om_EUR_a),
            total_annual=float(v.annual_hx_cost_EUR_a),
            heat=heat,
            el_per_heat=_array(v.el_per_heat, 'el_per_heat', (n,)),
            direct=_array(v.direct_fraction, 'direct_fraction', (n,)),
            air=air, direct_sources=source_direct,
            areas=area, investments=inv, om=om, annual=annual,
        )


    def _close(a, b, tol):
        return bool(np.all(np.abs(a-b) <= tol))


    def _profile_close(a, b, peak_tol_kW):
        """Lokaler UND kumulierter Unterschied, bei 1h-Raster in kWh.

        So werden sowohl einzelne echte Leistungsunterschiede als auch viele
        gleichgerichtete kleine Unterschiede erkannt. Kein Vergleich allein
        anhand einer Jahressumme, bei der sich Fehler wegheben koennten.
        """
        if a.shape != b.shape:
            return False
        delta = np.abs(a-b)
        return (bool(np.all(delta <= peak_tol_kW)) and
                float(np.sum(delta)) <= PROFILE_ABS_BUDGET_KWH)


    def _equivalent(a, b):
        if a.group != b.group:
            return False
        # Anlagenkonfiguration und Kosten QUELLENSCHARF pruefen.
        for name, tol in (
            ('heat_cap', CAPACITY_ATOL_KW),
            ('wp_cap', CAPACITY_ATOL_KW),
            ('total_area', AREA_ATOL_M2),
            ('total_investment', INVESTMENT_ATOL_EUR),
            ('total_om', OM_ATOL_EUR_A),
            ('total_annual', ANNUAL_COST_ATOL_EUR_A),
            ('areas', AREA_ATOL_M2),
            ('investments', INVESTMENT_ATOL_EUR),
            ('om', OM_ATOL_EUR_A),
            ('annual', ANNUAL_COST_ATOL_EUR_A),
        ):
            if not _close(getattr(a, name), getattr(b, name), tol):
                return False
        # Gleiche diskrete Industrie-/Luft-Umschaltstunden erforderlich.
        if not np.array_equal(a.air, b.air):
            return False
        # Neben der Heizleistung werden auch die EHDO-Koeffizienten geprueft.
        # Der anschliessende Vergleich der *effektiven* Leistungen verhindert,
        # dass groessere Anlagen allein wegen kleiner Anteilabweichungen
        # faelschlich zusammengefasst werden.
        for name, tol in (
            ('el_per_heat', EL_PER_HEAT_ATOL),
            ('direct', FRACTION_ATOL),
            ('direct_sources', FRACTION_ATOL),
        ):
            if not _close(getattr(a, name), getattr(b, name), tol):
                return False
        if not _profile_close(a.heat, b.heat, HEAT_ATOL_KW):
            return False
        if not _profile_close(
                a.heat*a.el_per_heat, b.heat*b.el_per_heat,
                EFFECTIVE_HEAT_ATOL_KW):
            return False
        if not _profile_close(
                a.heat*a.direct, b.heat*b.direct,
                EFFECTIVE_HEAT_ATOL_KW):
            return False
        if not _profile_close(
                a.direct_sources*a.heat[np.newaxis, :],
                b.direct_sources*b.heat[np.newaxis, :],
                EFFECTIVE_HEAT_ATOL_KW):
            return False
        return True


    def deduplicate(variants, sources):
        """Gibt (behaltene Varianten, Alias-Zuordnungen) in stabiler Reihenfolge.

        Aliase sind dicts mit 'duplikat_id' und 'gleichwertig_zu'. Varianten
        unterschiedlicher Kategorie werden gleich behandelt. Der erste
        Vertreter bleibt erhalten (single_source wird in generate() vor multi
        erzeugt). Kein Vergleichen nach TAC oder gerundeten Jahres-KPIs.
        """
        kept = []
        aliases = []
        groups: dict[tuple, list[_View]] = {}
        seen_ids: dict[str, _View] = {}
        repeated: dict[str, int] = {}
        for v in variants:
            current = _make_view(v, sources)
            if v.id in seen_ids:
                # Die bisherige Mehrquellen-Registry erzeugt gelegentlich
                # denselben HX-only-Betriebspunkt ueber zwei technische Wege
                # unter identischer ID. Auch diese Mehrfacherzeugung ist sicher
                # zu entfernen, solange die Profile wirklich uebereinstimmen.
                canonical = seen_ids[v.id]
                if not _equivalent(canonical, current):
                    raise ValueError(
                        f'WH1-DET Dubletten: ID {v.id} mehrfach fuer '
                        'UNTERSCHIEDLICHE Anlagen verwendet. Varianten-IDs korrigieren.'
                    )
                repeated[v.id] = repeated.get(v.id, 1) + 1
                alias_id = f'{v.id}#intern_{repeated[v.id]}'
            else:
                canonical = next((x for x in groups.get(current.group, ())
                                  if _equivalent(x, current)), None)
                seen_ids[v.id] = canonical if canonical is not None else current
                alias_id = v.id
            if canonical is None:
                kept.append(v)
                groups.setdefault(current.group, []).append(current)
            else:
                aliases.append(dict(duplikat_id=alias_id,
                                    gleichwertig_zu=canonical.variant.id,
                                    familie=v.family,
                                    auslegungsfaktor=v.factor,
                                    regel='gleiche Anlage; stundenweise und kumuliert max. 0.75 kWh numerische Profilabweichung'))

        return kept, aliases
    return _DetNamespace(**locals())
_dubletten = _init_dubletten()
del _init_dubletten

# ===========================================================================
# Originalbaustein: industrie_deterministisch_bounds.py
# ===========================================================================
def _init_bounds():
    # -*- coding: utf-8 -*-
    """Zertifizierbarer EHDO-Grenzabbruch, ausschliesslich im deterministischen Modus.

    Beim Minimierungs-MILP ist Gurobis BestBd eine *untere* Schranke. Eine
    Variante kann ohne Extraktion ihrer Primaerloesung ausgelassen werden, wenn
    BestBd >= (1 - GLOBAL_REL_GAP) * bisher_bestes_zulaessiges_TAC gilt.

    Kein zweiter Gurobi-Lauf; bisherige Solver-Optionen werden aus create_solver
    uebernommen. Legacy/Advanced bleiben von diesem Modul unberuehrt.
    """
    from contextlib import contextmanager, redirect_stdout
    from contextvars import ContextVar
    from dataclasses import dataclass
    from math import isfinite
    from pathlib import Path
    import re
    from typing import Optional

    # Globale GUARANTEE nur fuer nach Dublettenerkennung uebriggebliebene Varianten.
    GLOBAL_REL_GAP = 0.01
    # Technische Sicherheitszugabe in EUR/a oberhalb des mathematischen Schwellwerts.
    BOUND_STOP_ABS_MARGIN_EUR_A = 0.02

    @dataclass
    class BoundContext:
        candidate_id: str
        incumbent_EUR_a: Optional[float]
        lower_bound_EUR_a: Optional[float] = None
        solver_termination: str = ''
        solver_runtime_s: Optional[float] = None

    _context: ContextVar[Optional[BoundContext]] = ContextVar('wh1_det_bound_context', default=None)

    class BoundCase(Exception):
        def __init__(self, message, lower_bound_EUR_a=None, termination=''):
            super().__init__(message)
            self.lower_bound_EUR_a = lower_bound_EUR_a
            self.termination = termination

    class CandidatePruned(BoundCase):
        """Sicher: mathematischer BestBd reicht fuer den gemeinsamen 1%-Nachweis."""

    class CandidateInfeasible(BoundCase):
        """Solver hat bewiesen, dass diese technische Variante unzulaessig ist."""

    class CandidateUnresolved(BoundCase):
        """Keine verifizierte Primal-Loesung; LB kann spaeter ausreichend werden."""

    @contextmanager
    def bound_context(candidate_id, incumbent_EUR_a):
        value = float(incumbent_EUR_a) if incumbent_EUR_a is not None else None
        if value is not None and (not isfinite(value) or value <= 0):
            raise ValueError('WH1-BND: bisherige TAC muessen endlich und positiv sein')
        ctx = BoundContext(str(candidate_id), value)
        token = _context.set(ctx)
        try:
            yield ctx
        finally:
            _context.reset(token)


    def _finite(value):
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return None
        return number if isfinite(number) else None


    def _lower_bound(results):
        """Nur die vom Solver als LowerBound ausgewiesene mathematische Schranke.

        Keine Ableitung aus incumbent, Jahresenergie, Gurobi-Log oder gerundetem TAC.
        """
        problems = getattr(results, 'problem', None)
        for data in (problems, _first_problem(problems)):
            if data is None:
                continue
            lb = _finite(getattr(data, 'lower_bound', None))
            if lb is not None:
                return lb
        return None


    def _first_problem(problems):
        if problems is None:
            return None
        try:
            return problems[0]
        except (TypeError, IndexError, KeyError, AttributeError):
            return None


    def guaranteed_threshold(best_ub):
        """LB >= Schwelle ist hinreichend fuer den relativen globalen Gap."""
        return (1.0 - GLOBAL_REL_GAP) * float(best_ub)


    def certified_gap(best_ub, bounds):
        """Ohne Schranke eines Kandidaten kein Zertifikat (None)."""
        if not bounds or any(x is None for x in bounds):
            return None
        ub = _finite(best_ub)
        if ub is None or ub <= 0:
            return None
        lbs = [_finite(x) for x in bounds]
        if any(x is None for x in lbs):
            return None
        return max(0.0, (ub - min(lbs)) / abs(ub))


    def _trusted_solver_end(results, pyo):
        """NUMERIC/ERROR/SUBOPTIMAL duerfen keinen mathematischen Bound belegen."""
        term = results.solver.termination_condition
        if term in (pyo.TerminationCondition.optimal,
                    pyo.TerminationCondition.maxTimeLimit,
                    pyo.TerminationCondition.maxIterations,
                    pyo.TerminationCondition.maxEvaluations):
            return True
        if term == pyo.TerminationCondition.other:
            # USER_OBJ_LIMIT; SUBOPTIMAL ist ebenfalls 'other', aber unzuverlaessig.
            message = str(getattr(results.solver, 'termination_message', '') or '')
            message += ' ' + str(getattr(results.solver, 'message', '') or '')
            return ('User specified an objective limit' in message
                    or 'user objective limit' in message.lower())
        return False


    def execute(model, pyomo_config, model_name, result_dir):
        """Ersetzt NUR im DET-EHDO den Aufruf execute_and_diagnose().

        - Berechnet bei bekanntem Incumbent Gurobis BestBdStop zusaetzlich.
        - Wenn ausreichende untere Schranke: CandidatePruned, KEIN Ergebnisexport.
        - Bei regularem 'optimal' (einschl. konfiguriertem 1%-MIPGap):
          laedt das originale Pyomo-Solverergebnis, danach unveraenderter Export.
        - Bei Abbruch ohne hinreichenden Bound: CandidateUnresolved, kein Gewinner.
        - Bei fehlendem/ungueltigem Bound: fail closed.
        """
        ctx = _context.get()
        if ctx is None:
            raise RuntimeError('WH1-BND: EHDO ohne aktiven Varianten-Kontext aufgerufen')
        from districtgenerator.functions import solver_config
        import pyomo.environ as pyo

        # Nicht global die Basis-Solveroptionen aendern.
        if pyomo_config.get('solver_name', '').lower() != 'gurobi':
            raise RuntimeError('WH1-BND: zertifizierter BestBdStop erfordert Solver gurobi')
        solver, options = solver_config.create_solver(pyomo_config=pyomo_config)
        options = dict(options)
        if ctx.incumbent_EUR_a is not None:
            threshold = guaranteed_threshold(ctx.incumbent_EUR_a)
            options['BestBdStop'] = threshold + BOUND_STOP_ABS_MARGIN_EUR_A
            print(f'[WH1-BND] {ctx.candidate_id}: globales LB-Abbruchziel '
                  f'{threshold:.4f} EUR/a (BestBdStop mit Sicherheitszugabe).')
        # Im Gegensatz zu execute_and_diagnose(): Bei BestBdStop KEINE neue Optimierung.
        # Die regulaere Gesamtzeit, MIPGap, Threads, FeasTol bleiben aus create_solver().
        safe_id = re.sub(r'[^0-9A-Za-z_.-]', '_', ctx.candidate_id)[:100]
        log = Path(result_dir) / f'solver_output_{model_name}_{safe_id}.log'
        log.parent.mkdir(parents=True, exist_ok=True)
        # Niemals versehentlich die Loesungsdatei eines vorherigen Kandidaten nutzen.
        previous_solution = Path(result_dir) / f'solution_file_{model_name}.txt'
        if previous_solution.is_file():
            previous_solution.unlink()
        with log.open('w', encoding='utf-8') as stream:
            with redirect_stdout(stream):
                results = solver.solve(model, tee=True, options=options,
                                       load_solutions=False)
        ctx.solver_termination = str(results.solver.termination_condition)
        ctx.solver_runtime_s = _finite(getattr(results.solver, 'time', None))
        if ctx.solver_runtime_s is None:
            ctx.solver_runtime_s = _finite(getattr(results.solver, 'wall_time', None))
        ctx.lower_bound_EUR_a = _lower_bound(results)
        lb = ctx.lower_bound_EUR_a
        term = results.solver.termination_condition
        print(f'[WH1-BND] {ctx.candidate_id}: term={term}, '
              f'LB={lb if lb is not None else "nicht vorhanden"}; Log: {log}')

        if term == pyo.TerminationCondition.infeasible:
            raise CandidateInfeasible('Gurobi hat Unzulaessigkeit bewiesen',
                                      None, str(term))
        if lb is None or not _trusted_solver_end(results, pyo):
            ctx.lower_bound_EUR_a = None
            raise CandidateUnresolved('Keine vertrauenswuerdige endliche untere Schranke '
                                      'aus dem Pyomo/Gurobi-Solverergebnis',
                                      None, str(term))
        # Zuerst Pruning, auch wenn 'optimal' mit 1% interner Gap-Grenze erreicht.
        if ctx.incumbent_EUR_a is not None and lb >= guaranteed_threshold(ctx.incumbent_EUR_a):
            raise CandidatePruned('Globale untere Schranke erreicht', lb, str(term))
        if term != pyo.TerminationCondition.optimal:
            raise CandidateUnresolved(f'Gurobi-Abbruch ohne genuegenden LB: {term}',
                                      lb, str(term))
        if not len(results.solution):
            raise CandidateUnresolved('Solver meldet optimal, liefert aber keine '
                                      'ladbare Primal-Loesung', lb, str(term))
        # Extraktion in opti_dimensioning_central_devices.py ist unveraendert.
        model.solutions.load_from(results)
        return results
    return _DetNamespace(**locals())
_bounds = _init_bounds()
del _init_bounds

# ===========================================================================
# Originalbaustein: industrie_deterministisch_pyomo.py
# ===========================================================================
def _init_pyomo():
    # -*- coding: utf-8 -*-
    """Kleine WH1-EHDO-Schnittstelle fuer feste thermische Varianten.

    Auswahl einer Variante geschieht AUSSERHALB von Pyomo durch den Runner;
    stuendlich frei bleibt nur die Nutzungsleistung x in [0, Angebot].
    Die vorhandenen EH1-/TES-Bilanzen und Solverparameter werden beibehalten.
    """
    import numpy as np


    def _selected(data):
        ind=getattr(data,'industry_optimization',None)
        if not isinstance(ind,dict) or 'det_selected' not in ind:
            raise ValueError('WH1-DET: keine ausgewaehlte Variante. EHDO-Runner muss zuerst laufen.')
        return ind['det_selected'],ind


    def _hour_map(data, steps, *, design=False, param=None, cluster=None):
        from districtgenerator.functions import industrie_optimierung_bridge as bridge
        if design:
            for d, original in enumerate(param['typedays']):
                sl=bridge._week(data,int(original),steps)
                for t,hour in enumerate(range(sl.start,sl.stop)):
                    yield (d,t),hour
        else:
            selected=list(getattr(data,'clusters',[]))
            if cluster is None or int(cluster)>=len(selected):
                raise ValueError('WH1-DET: ungueltiger Betriebscluster')
            sl=bridge._week(data,int(selected[int(cluster)]),steps)
            for t,hour in enumerate(range(sl.start,sl.stop)):
                yield (t,),hour


    def _hydraulic_gross_cap_kW(data, n_hours, *, demand_cap_kW=None):
        """WH1-Bruttogrenze passend zur unveraenderten Netz-Postplot-Hydraulik.

        Der Postplot setzt m_WH = Q_gross/(cp*(T_supply-T_return)) und fordert
        m_WH <= Summe der Gebaeudemassenstroeme. Deshalb MUSS auch die
        Optimierung Q_gross auf genau diese stundenweise Leistung begrenzen.

        Bei Null-Temperaturhub und Null-Netzbedarf ist Bruttoeinspeisung = 0.
        Ein dennoch im Netzprofil vorhandener Gebaeudemassenstrom wird hier nicht
        als thermische Last interpretiert und fuehrt nicht zum Abbruch.
        Positiver Bedarf ohne positiven Temperaturhub bleibt ein Datenfehler.
        Ohne demand_cap_kW gilt die historische strengere Validierung, um
        bestehende direkte Aufrufer nicht unbemerkt anders zu behandeln.

        Keine Limitierung der WH1-Produktion: Mehrproduktion fuer einen
        Industrie-TES ist erlaubt, solange die Brutto-Netzeinspeisung passt.
        """
        param = getattr(data, '_industry_network_plot_param', None)
        if not isinstance(param, dict) or 'building_massflow_HX' not in param:
            raise RuntimeError(
                'WH1-DET: Gebaeudemassenstroeme fuer hydraulische '
                'WH1-Bruttogrenze fehlen (_industry_network_plot_param).'
            )
        grid = data.heat_grid_data
        ts = np.asarray(grid['T_supply_EH'], dtype=float)
        tr = np.asarray(grid['T_return_EH'], dtype=float)
        cp = float(grid['fluid']['c_f'])
        if (cp <= 0 or not np.isfinite(cp)
                or ts.shape != (n_hours,) or tr.shape != (n_hours,)
                or not np.isfinite(ts).all() or not np.isfinite(tr).all()):
            raise ValueError('WH1-DET: ungueltige Netztemperaturen/Fluiddaten.')

        mass = np.zeros(n_hours, dtype=float)
        for node, value in param['building_massflow_HX'].items():
            arr = np.asarray(value, dtype=float)
            if (arr.shape != (n_hours,) or not np.isfinite(arr).all()
                    or np.any(arr < -1e-9)):
                raise ValueError(
                    f'WH1-DET: ungueltige Gebaeudemassenstroeme fuer {node!r}.'
                )
            mass += arr
        if np.any(mass < -1e-9):
            raise ValueError('WH1-DET: negativer Gebaeudemassenstrom.')

        delta_t = ts - tr
        no_lift = delta_t <= 1e-9
        if demand_cap_kW is None:
            # Abwaertskompatibel fuer direkte Aufrufe ohne Nachfrageprofil.
            # Fuer die EHDO wird das Nachfrageprofil immer explizit uebergeben.
            invalid = no_lift & (mass > 1e-9)
            reason = 'positiver Gebaeudemassenstrom'
        else:
            demand = np.asarray(demand_cap_kW, dtype=float)
            if (demand.shape != (n_hours,) or not np.isfinite(demand).all()
                    or np.any(demand < -1e-9)):
                raise ValueError('WH1-DET: ungueltiges Nachfrageprofil fuer Hydraulikpruefung.')
            # Gebaeudemassenstrom und Gebaeudewaermebedarf sind nicht synonym.
            # Stunden ohne thermischen Hub UND ohne Nachfrage bleiben inaktiv,
            # auch wenn der gespeicherte Massestrom dort einen positiven Wert hat.
            invalid = no_lift & (demand > 1e-8)
            reason = 'positiver Netzbedarf'
        if np.any(invalid):
            t = int(np.flatnonzero(invalid)[0])
            extra = (f', Bedarf={demand[t]:.8g} kW'
                     if demand_cap_kW is not None else '')
            raise ValueError(
                f'WH1-DET: {reason} ohne positiven Netztemperaturhub; '
                f'Stunde {t}: T_supply={ts[t]:.6g} C, '
                f'T_return={tr[t]:.6g} C, '
                f'Gebaeudemassenstrom={mass[t]:.8g} kg/s{extra}; '
                f'insgesamt {int(np.count_nonzero(invalid))} betroffene Stunden.'
            )
        cap = np.maximum(0.0, mass * cp * np.maximum(delta_t, 0.0) / 1000.0)
        # Bei fehlendem Netztemperaturhub kann WH1 grundsaetzlich nicht
        # hydraulisch ins Quartiersnetz einspeisen; keine Division durch 0.
        cap[no_lift] = 0.0
        return cap


    def _safe_gross_cap_kW(demand_cap_kW, hydraulic_cap_kW):
        """Beide unabhaengigen Netzgrenzen fuer BRUTTO-WH1 einhalten."""
        demand = float(demand_cap_kW)
        hydraulic = float(hydraulic_cap_kW)
        if not (np.isfinite(demand) and np.isfinite(hydraulic)
                and demand >= 0 and hydraulic >= 0):
            raise ValueError('WH1-DET: ungueltige hydraulische Bruttoeinspeisegrenze.')
        return min(demand, hydraulic)


    def _add_core(m,data,variant,ind,keys,*,design,devs=None):
        import pyomo.environ as pyo
        from districtgenerator.functions import industrie_optimierung_bridge as bridge
        S=ind['source_input'].shape[0]
        m.wh_deterministic=True
        m.wh_det_variant_id=variant.id
        m.wh_det_variant=variant
        m.wh_sources=pyo.RangeSet(0,S-1)
        # Vollstaendig indexierte Stundenmenge, um beide EHDO-/Betriebsformen abzudecken.
        ids=list(keys)
        nd=3 if design else 1
        m.wh_det_keys=pyo.Set(dimen=nd,initialize=ids)
        m.wh_heat=pyo.Var(m.wh_det_keys,within=pyo.NonNegativeReals)  # kW in EHDO, W im Betrieb
        m.wh_on=pyo.Var(m.wh_det_keys,within=pyo.Binary)
        m.wh_net=pyo.Var(m.wh_det_keys,within=pyo.NonNegativeReals)
        m.wh_constraints=pyo.ConstraintList()
        tes_on=(bridge._tes_design_variables(m,data,devs) if design
                else bridge._tes_operating_variables(m,data))
        ratio=1. if design else 1000.
        # Modellwerte sind bewusst *linear* in der Nutzungsvariable.
        # Aenderungen an einer Variantenfamilie erfordern nur neue Jahresprofile.
        # Postplot verwendet BRUTTOeinspeisung fuer m_WH, nicht die nach
        # Anschlussleitungsverlusten verbleibende NETTOeinspeisung.
        # Gleiche stundenweise Obergrenze daher bereits in der EHDO/Cluster-MILP.
        hydraulic_gross_cap = _hydraulic_gross_cap_kW(
            data, len(ind['demand_cap']), demand_cap_kW=ind['demand_cap'])
        # Quellenanteile fuer ALLE direkten HX und eine feste industrielle WP-Quelle.
        per_source_direct = variant.per_source_arrays(S)[4]
        wp_source = (variant.wp_industry_source_id
                     if variant.hx_areas_by_source_m2 else variant.source_id)
        if wp_source >= S:
            raise ValueError('WH1-DET: WP-Anschlussquelle ausserhalb der Quelleingabe')
        spec={}
        for key,hour in keys.items():
            maxq=float(variant.heat_max_kW[hour])
            loss=float(ind['nominal_loss'][hour])
            demand=float(ind['demand_cap'][hour])
            frac=float(variant.direct_fraction[hour])
            el=float(variant.el_per_heat[hour])
            if not (np.isfinite([maxq,loss,demand,frac,el]).all()
                    and maxq>=0 and loss>=0 and demand>=0
                    and -1e-8<=frac<=1+1e-8 and 0<=el<1):
                raise ValueError(f'WH1-DET: ungueltiges Variantenprofil Stunde {hour}')
            air=float(variant.air_share[hour]) if len(variant.air_share) else 0.
            if air not in (0.,1.):raise ValueError('WH1-DET: Luft/Industrie-Modus ungueltig')
            spec[key]=(maxq,loss,demand,frac,el,air)
            m.wh_constraints.add(m.wh_heat[key] <= ratio*maxq)
            charge=(m.wh_tes_charge[key] if tes_on else 0)
            discharge=(m.wh_tes_discharge[key] if tes_on else 0)
            gross=m.wh_heat[key]-charge+discharge
            # TES darf nur von WH1, nicht heimlich von EH1 oder aus TES selbst laden.
            if tes_on:
                m.wh_constraints.add(charge <= m.wh_heat[key])
            m.wh_constraints.add(gross >= 0)
            # Die alte Grenze 'demand + loss' war hydraulisch zu gross:
            # gross/(cp*dT) durfte den Gebaeudemassenstrom ueberschreiten.
            # Das Minimum deckt ausserdem kleine Differenzen der im Netz und
            # in der Bridge verwendeten Nachfrage-/Temperaturprofile ab.
            gross_cap = _safe_gross_cap_kW(demand, hydraulic_gross_cap[hour])
            m.wh_constraints.add(gross <= ratio*gross_cap*m.wh_on[key])
            m.wh_constraints.add(m.wh_net[key] == gross-ratio*loss*m.wh_on[key])
            m.wh_constraints.add(m.wh_net[key] <= ratio*demand)
            if maxq<=1e-9:m.wh_heat[key].fix(0)
        m.wh_det_spec=spec
        m.wh_gross=pyo.Expression(m.wh_det_keys,rule=lambda mm,*i:
            mm.wh_heat[i] - (mm.wh_tes_charge[i]-mm.wh_tes_discharge[i] if tes_on else 0))
        m.wh_hp_el=pyo.Expression(m.wh_det_keys,rule=lambda mm,*i:
            mm.wh_heat[i]*spec[i][4])
        # Legacy-kompatible Quelle-zu-Verwendungs-Art-Profile in derselben
        # Einheit wie die jeweilige Ebene. Ohne zusaetzliche freie Variablen.
        m.wh_direct=pyo.Expression(m.wh_sources,m.wh_det_keys,
            rule=lambda mm,s,*i: mm.wh_heat[i]*float(per_source_direct[int(s),keys[i]]))
        def hp_expr(mm,s,*i):
            if int(s)!=wp_source or variant.wp_kind!='normal':return 0.
            return mm.wh_heat[i]*(1-spec[i][3])
        m.wh_hp=pyo.Expression(m.wh_sources,m.wh_det_keys,rule=hp_expr)
        if variant.wp_kind=='dual':
            m.wh_dual_ind=pyo.Expression(m.wh_sources,m.wh_det_keys,
                rule=lambda mm,s,*i: mm.wh_heat[i]*(1-spec[i][3])*(1-spec[i][5])
                if (int(s)==wp_source) else 0.)
            m.wh_dual_air=pyo.Expression(m.wh_det_keys,
                rule=lambda mm,*i: mm.wh_heat[i]*(1-spec[i][3])*spec[i][5])
            m.wh_dual_ind_el=pyo.Expression(m.wh_det_keys,
                rule=lambda mm,*i: mm.wh_hp_el[i]*(1-spec[i][5]))
            m.wh_dual_air_el=pyo.Expression(m.wh_det_keys,
                rule=lambda mm,*i: mm.wh_hp_el[i]*spec[i][5])
            m.wh_dual_mode=pyo.Param(m.wh_det_keys,initialize=lambda mm,*i:
                int(spec[i][5]),within=pyo.Binary)
        if design:bridge._tes_design_constraints(m,data)
        else:bridge._tes_operating_constraints(m,data)
        return spec


    def add_design(model,data,param,steps,devs):
        import pyomo.environ as pyo
        from districtgenerator.functions import industrie_optimierung_bridge as bridge
        v,ind=_selected(data)
        ids={ (y,d,t):hour for (d,t),hour in _hour_map(data,steps,design=True,param=param)
              for y in model.support_years }
        _add_core(model,data,v,ind,ids,design=True,devs=devs)
        S=ind['source_input'].shape[0]
        # Feste Anlagenentscheidung; keine Szenario-/Quellenwahl im Pyomo-MILP.
        model.wh_hp_cap=pyo.Param(initialize=v.wp_cap_kW if v.wp_kind=='normal' else 0.)
        if v.wp_kind=='dual':
            model.wh_dual_cap=pyo.Param(initialize=v.wp_cap_kW)
        hx_areas=v.per_source_arrays(S)[0]
        model.wh_hx_area=pyo.Param(model.wh_sources,initialize=lambda mm,s:
            float(hx_areas[int(s)]))
        # Alt-Exporter verlangt kW-HX-Container. Fuer den deterministischen Modus
        # sind m2-Kosten eigenstaendig; keine falsche EUR/kW-Nachberechnung.
        model.wh_hx_cap=pyo.Param(model.wh_sources,initialize=0.)
        model.wh_hx_built=pyo.Param(model.wh_sources,initialize=0.)
        model.wh_hx_inv_per_kw=[0.]*S
        model.wh_hx_om_per_year=[0.]*S
        model.wh_hx_ann_factor=[0.]*S
        model.wh_hx_q_codes=[str(x) for x in ind['det_input'].q_codes]
        rate=bridge.WH_HP_INV_EUR_PER_KW if v.wp_kind=='normal' else bridge.WH_DUAL_INV_EUR_PER_KW
        rate=0. if v.wp_kind=='none' else rate
        interest=float(param['interest_rate']);years=bridge.WH_HP_LIFE_YEARS
        annuity = _varianten.annuity
        caprate=rate*(annuity(interest,years)+bridge.WH_HP_OM_FRACTION)
        model.wh_annual_capex=pyo.Expression(expr=model.wh_hp_cap*caprate)
        if v.wp_kind=='dual':
            model.wh_dual_annual_cost=pyo.Expression(expr=model.wh_dual_cap*caprate)
        model.wh_hx_annual_cost=pyo.Expression(expr=v.annual_hx_cost_EUR_a)
        print(f'[WH1-DET] EHDO {v.id}: HX={v.hx_area_m2:.2f} m2, '
              f'WP={v.wp_cap_kW:.1f} kW, Angebotmax={max(v.heat_max_kW):.1f} kW')
        return ind


    def add_operation(model,data,cluster,steps):
        import pyomo.environ as pyo
        from districtgenerator.functions import industrie_optimierung_bridge as bridge
        v,ind=_selected(data)
        caps=getattr(data,'centralDevices',{}).get('capacities',{})
        installed=caps.get('industry_deterministic_variant_id')
        if installed!=v.id:
            raise ValueError(f'WH1-DET: Betriebsvariante {v.id} stimmt nicht mit EHDO '
                             f'({installed}) ueberein; kein stiller Rueckfall')
        ids={key:hour for key,hour in _hour_map(data,steps,cluster=cluster)}
        _add_core(model,data,v,ind,ids,design=False)
        model.wh_base_loss_W=pyo.Param(model.t,initialize=lambda mm,t:
            float(ind['base_losses'][ids[(t,)]])*1000.)
        return ind


    def design_result(model,result):
        """Fixe WH1-HX-Flaechenkosten in Berichts-KPIs aufnehmen, NICHT zweimal
        in der EHDO-Zielfunktion (dort schon via wh_hx_annual_cost enthalten)."""
        v=model.wh_det_variant
        S=len(list(model.wh_sources))
        areas,inv,om,annual,profiles=v.per_source_arrays(S)
        ann=annual-om
        caps=[max(float(v.heat_max_kW[t]*profiles[s,t])
                  for t in range(v.heat_max_kW.size)) for s in range(S)]
        result.update(dict(industry_thermal_model='deterministic',
            industry_deterministic_variant_id=v.id,
            industry_deterministic_family=v.family,
            industry_deterministic_source_id=v.source_id,
            industry_deterministic_demand_factor=v.factor,
            industry_deterministic_wp_source_id=(v.wp_industry_source_id
                if v.hx_areas_by_source_m2 else v.source_id),
            industry_deterministic_included_sources=list(v.included_source_ids),
            industry_deterministic_excluded_sources=list(v.excluded_source_ids),
            industry_hx_areas_m2=list(areas),
            industry_hx_capacities_kW=list(caps),
            industry_hx_q_codes=list(model.wh_hx_q_codes),
            industry_hx_investment_EUR_by_source=list(inv),
            industry_hx_annuity_EUR_a_by_source=list(ann),
            industry_hx_om_EUR_a_by_source=list(om),
            industry_hx_annual_cost_EUR_a=v.annual_hx_cost_EUR_a,
            industry_hx_total_annual_cost_EUR_a=v.annual_hx_cost_EUR_a,
        ))
        # Die alte Postprocess-Berechnung hat fuer die Platzhalter-HX-Kapazitaeten
        # 0 EUR addiert. Die tatsaechlichen Flaechenkosten werden JETZT ergaenzt.
        for key,value in [('total_inv_cost',v.hx_investment_EUR),
                          ('total_inv_cost_unsubsidized',v.hx_investment_EUR),
                          ('total_ann_inv_cost',sum(ann)),
                          ('total_ann_inv_cost_unsubsidized',sum(ann)),
                          ('total_om_cost',v.hx_om_EUR_a)]:
            result[key]=result.get(key,0)+int(round(value))


    def operating_result(model):
        import pyomo.environ as pyo
        if not getattr(model,'wh_deterministic',False):return None
        return_dict={
            'direct_W': [[float(pyo.value(model.wh_direct[s,t])) for t in model.t]
                         for s in model.wh_sources],
            'hp_output_W': [[float(pyo.value(model.wh_hp[s,t])) for t in model.t]
                            for s in model.wh_sources],
            'gross_W': [float(pyo.value(model.wh_gross[t])) for t in model.t],
            'net_W': [float(pyo.value(model.wh_net[t])) for t in model.t],
            'hp_electric_W': [float(pyo.value(model.wh_hp_el[t])) for t in model.t],
            'connection_loss_W': [float(pyo.value(model.wh_gross[t]-model.wh_net[t]))
                                  for t in model.t],
            'thermal_model':'deterministic',
            'deterministic_variant_id':model.wh_det_variant_id,
        }
        if hasattr(model,'wh_tes_soc'):
            return_dict.update(tes_charge_W=[float(pyo.value(model.wh_tes_charge[t])) for t in model.t],
                tes_discharge_W=[float(pyo.value(model.wh_tes_discharge[t])) for t in model.t],
                tes_soc_Wh=[float(pyo.value(model.wh_tes_soc[t])) for t in model.t])
        if hasattr(model,'wh_dual_air'):
            return_dict.update(
                dual_industrial_W=[[float(pyo.value(model.wh_dual_ind[s,t])) for t in model.t]
                                   for s in model.wh_sources],
                dual_air_W=[float(pyo.value(model.wh_dual_air[t])) for t in model.t],
                dual_industrial_electric_W=[float(pyo.value(model.wh_dual_ind_el[t])) for t in model.t],
                dual_air_electric_W=[float(pyo.value(model.wh_dual_air_el[t])) for t in model.t],
                dual_mode=[int(pyo.value(model.wh_dual_mode[t])) for t in model.t],
            )
        return return_dict
    return _DetNamespace(**locals())
_pyomo = _init_pyomo()
del _init_pyomo

# ===========================================================================
# Originalbaustein: industrie_deterministisch_runner.py
# ===========================================================================
def _init_runner():
    # -*- coding: utf-8 -*-
    """WH1 Deterministik: separate EHDO-Laeufe, korrekter Gesamtkostenvergleich.

    Kein automatischer Legacy-/Advanced-Fallback. Alte EHDO-Solverparameter bleiben
    pro Kandidat erhalten. Gescheiterte Kandidaten werden dokumentiert; wenn alle
    scheitern, bricht das gesamte Experiment ab.
    """
    import copy
    import csv
    import json
    import os
    from pathlib import Path
    import shutil
    import warnings

    vmod = _varianten
    bnd = _bounds

    # Zum Integrationstest 1 oder 3, fuer den regulaeren Vergleich None verwenden.
    TEST_MAX_VARIANTS = None
    SELECTED_CATEGORIES = ('single_source', 'multi_source_cascade')
    REQUIRE_GLOBAL_CERTIFICATE = True  # kein Sieger ohne nachgewiesenen Gesamt-Gap
    # Unterhalb eines Cents/a darf keine nichtreproduzierbare Gurobi-Rundung
    # die Gewinner-ID wechseln. Bei Gleichstand bleibt die erste Variante.
    TAC_TIE_ABS_EUR_A = 0.01


    def _write_report(folder, rows, best=None, aliases=(), expected_count=None, full_catalog=True):
        folder.mkdir(parents=True, exist_ok=True)
        costs = {r['id']: r['ehdo_tac_EUR_a'] for r in rows
                 if r.get('status') == 'optimal' and 'ehdo_tac_EUR_a' in r}
        skipped = []
        for alias in aliases:
            record = dict(alias)
            canonical = record['gleichwertig_zu']
            record['status'] = ('gleicher_betriebspunkt_nicht_separat_geloest'
                                if canonical in costs else 'referenz_nicht_geloest')
            if canonical in costs:
                record['ehdo_tac_EUR_a'] = costs[canonical]
            else:
                canonical_row = next((r for r in rows if r['id'] == canonical), None)
                if canonical_row is not None:
                    record['referenz_status'] = canonical_row.get('status')
                    record['referenz_lower_bound_EUR_a'] = canonical_row.get('lower_bound_EUR_a')
            skipped.append(record)
        with (folder / 'vergleich.json').open('w', encoding='utf-8') as f:
            proven_lbs = [r.get('lower_bound_EUR_a') for r in rows
                          if r.get('status') != 'infeasible_certified']
            winners = [r for r in rows if r.get('status') == 'optimal']
            best_ub = min((r['ehdo_tac_EUR_a'] for r in winners), default=None)
            global_gap = bnd.certified_gap(best_ub, proven_lbs)
            finished = expected_count is not None and len(rows) == expected_count
            json.dump({'winner': best, 'variants': rows,
                       'deduplicated_variants': skipped,
                       'evaluated_count': len(rows),
                       'skipped_duplicates_count': len(skipped),
                       'global_gap': global_gap,
                       'global_gap_target': bnd.GLOBAL_REL_GAP,
                       'global_certificate': bool(finished and full_catalog and
                                                  global_gap is not None and
                                                  global_gap <= bnd.GLOBAL_REL_GAP),
                       'all_candidates_processed': finished,
                       'expected_count': expected_count,
                       'certificate_scope': ('unique_variants_after_approximate_deduplication'
                                             if full_catalog else 'test_subset_only')},
                      f, indent=2, ensure_ascii=False, allow_nan=False)
        if rows:
            columns = list(dict.fromkeys(k for r in rows for k in r))
            with (folder / 'vergleich.csv').open('w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=columns, delimiter=';')
                writer.writeheader()
                writer.writerows(rows)
        with (folder / 'dubletten.csv').open('w', newline='', encoding='utf-8-sig') as f:
            columns = ['duplikat_id', 'gleichwertig_zu', 'familie',
                       'auslegungsfaktor', 'regel', 'status', 'ehdo_tac_EUR_a']
            writer = csv.DictWriter(f, fieldnames=columns, delimiter=';',
                                    extrasaction='ignore')
            writer.writeheader()
            writer.writerows(skipped)


    def run_all(data,devs,param,dem,result_dict,run_single):
        """Call-Back run_single(data,devs,param,dem,new_result) loest EINEN EHDO-Lauf.

        Verwendet dieselben geclusterten Netz-/Nachfragedaten fuer jeden Fall.
        'tac_exact_EUR_a' wird verglichen, NICHT ein Vorab-PFA-Proxy.
        """
        ind=getattr(data,'industry_optimization',None)
        if not isinstance(ind,dict):
            raise RuntimeError('WH1-DET: Netz-/Quellenbridge fehlt vor EHDO')
        if data.heat_grid_data.get('industrial_dispatch_mode')!='optimizer':
            raise ValueError('WH1-DET: erfordert Einsatzstrategie 2 (optimizer)')
        if abs(float(param.get('optimization_focus',0.0)))>1e-12:
            raise ValueError('WH1-DET: Kostenvergleich erfordert optimization_focus=0 '
                             '(EHDO auf TAC statt CO2 optimieren).')
        if 'det_input' not in ind:
            raise RuntimeError('WH1-DET: thermische Eingabedaten in Bridge nicht geladen')
        inp=ind['det_input']
        # Zinssatz von EHDO muss in technischer HX-Annuitaet identisch sein.
        inp.interest_rate=float(param['interest_rate'])
        inp.validate()
        issues=vmod.monthly_plateau_audit(inp.source_kW)
        if issues:
            warnings.warn('WH1-DET: Eingangsprofile weichen in einzelnen Monaten '
                          f'von konstanter eingeschalteter Leistung ab; Beispiele: {issues[:5]}')
        for source_id,tin in enumerate(inp.source_in_C):
            power=inp.source_kW[source_id]
            lift=tin-inp.ambient_C
            excluded=(power>1e-9)&(lift<=1e-6)
            if excluded.any():
                warnings.warn(f'WH1-DET Quelle {source_id}: {excluded.sum()} Stunden mit '
                              f'TQuelle <= Tamb; {power[excluded].sum():.1f} kWh/a '
                              'konservativ nicht als Industriequelle nutzbar.')
            near=(power>1e-9)&(lift>1e-6)&(lift<1.0)
            if near.any():
                warnings.warn(f'WH1-DET Quelle {source_id}: {near.sum()} Stunden '
                              'mit weniger als 1 K Quelle-Umgebung; Cdot=PFA/DeltaT '
                              'kann sehr gross werden. Physikalisch validieren.')
        candidates, aliases = vmod.generate(
            inp, SELECTED_CATEGORIES, return_deduplication=True)
        total_before_dedup = len(candidates) + len(aliases)
        print(f'[WH1-DET] {total_before_dedup} Varianten erzeugt; '
              f'{len(aliases)} technische Dubletten uebersprungen; '
              f'{len(candidates)} unabhaengige EHDO-Kandidaten.')
        if TEST_MAX_VARIANTS is not None:
            candidates=candidates[:int(TEST_MAX_VARIANTS)]
        if not candidates:
            raise ValueError('WH1-DET: keine technischen Varianten erzeugt')
        root=Path('optimization_results')/'wh1_deterministische_varianten'
        root.mkdir(parents=True,exist_ok=True)
        if os.environ.get('WH1_DET_DIAG_ONLY','0')=='1':
            rows=[dict(v.summary(),status='nur_thermik') for v in candidates]
            _write_report(root,rows,None,aliases,expected_count=len(candidates),
                          full_catalog=TEST_MAX_VARIANTS is None)
            print(f'[WH1-DET] Thermische Diagnosedaten ohne EHDO unter {root}')
            raise SystemExit(0)
        rows=[];best=None;best_cost=float('inf');best_result=None
        saved_sol=None
        print(f'[WH1-DET] {len(candidates)} unterschiedliche Varianten '
              '(Einzelquellen, Mehrquellen + Baseline).')
        print(f'[WH1-BND] Gemeinsames Ziel: {bnd.GLOBAL_REL_GAP:.1%} Gap; '
              'Konfigurationen nach vorhandener Dublettenerkennung.')
        try:
            for idx,variant in enumerate(candidates,1):
                ind['det_selected']=variant
                row=variant.summary()
                print(f'[WH1-DET] EHDO {idx}/{len(candidates)}: {variant.id} ...')
                try:
                    incumbent = best_cost if best is not None else None
                    with bnd.bound_context(variant.id, incumbent) as bc:
                        candidate_result=run_single(
                            data,devs,param,dem,copy.deepcopy(result_dict))
                    if not isinstance(candidate_result,dict):
                        raise RuntimeError('EHDO lieferte keine gueltige Loesung')
                    cost=float(candidate_result.get('tac_exact_EUR_a',float('nan')))
                    if not (float('-inf')<cost<float('inf')):
                        raise ValueError('Keine endlichen TAC aus EHDO')
                    if bc.lower_bound_EUR_a is None:
                        raise RuntimeError('Loesung ohne gueltigen Solver-BestBd')
                    if bc.lower_bound_EUR_a > cost + 0.05:
                        raise RuntimeError('Solver-LB groesser als zulaessige EHDO-TAC; '
                                           'unterschiedliche Zielfunktionen?')
                    row.update(status='optimal',ehdo_tac_EUR_a=cost,
                               lower_bound_EUR_a=bc.lower_bound_EUR_a,
                               solver_termination=bc.solver_termination)
                    # Cent-Gleichstand fuehrt nicht zu zufaellig wechselnder Variante.
                    if cost < best_cost - TAC_TIE_ABS_EUR_A:
                        src=Path('optimization_results')/'solution_file_ehdo_model.txt'
                        target=root/'gewinner_solution_file_ehdo_model.txt'
                        if not src.is_file():
                            raise RuntimeError('EHDO-Solution-Datei des Gewinners fehlt')
                        shutil.copy2(src,target)
                        saved_sol=target
                        best_cost=cost;best=variant;best_result=candidate_result
                except bnd.CandidatePruned as exc:
                    row.update(status='bound_pruned',
                               lower_bound_EUR_a=exc.lower_bound_EUR_a,
                               solver_termination=exc.termination,
                               proof='LB >= (1-global_gap)*bisheriges_bestes_TAC')
                    print(f'[WH1-BND] {variant.id}: sicher vorzeitig beendet; '
                          f'LB={exc.lower_bound_EUR_a:.2f} EUR/a.')
                except bnd.CandidateInfeasible as exc:
                    row.update(status='infeasible_certified',
                               lower_bound_EUR_a=None,
                               solver_termination=exc.termination)
                    print(f'[WH1-BND] {variant.id}: nachgewiesen unzulaessig.')
                except bnd.CandidateUnresolved as exc:
                    row.update(status='bound_only_unresolved',
                               lower_bound_EUR_a=exc.lower_bound_EUR_a,
                               solver_termination=exc.termination,
                               error=str(exc))
                    print(f'[WH1-BND] {variant.id}: kein eigener Sieger, '
                          f'LB={exc.lower_bound_EUR_a}; {exc}')
                except (KeyboardInterrupt,SystemExit):
                    raise
                except Exception as exc:
                    # Ohne endliche Schranke auch kein mathematischer Nachweis.
                    row.update(status='fehler', lower_bound_EUR_a=None,
                               error=f'{type(exc).__name__}: {exc}')
                    print(f'[WH1-DET] {variant.id}: {row["error"]}')
                rows.append(row)
                _write_report(root,rows,best.id if best else None,aliases,
                              expected_count=len(candidates),
                              full_catalog=TEST_MAX_VARIANTS is None)
            if best is None:
                raise RuntimeError('WH1-DET: Keine gueltige EHDO-Incumbent-Loesung; '
                                   f'Diagnose: {root/"vergleich.json"}')
            # Die zertifizierte Unzulaessigkeit ist eine unendliche untere Schranke.
            relevant = [r for r in rows if r.get('status') != 'infeasible_certified']
            lbs=[r.get('lower_bound_EUR_a') for r in relevant]
            gap=bnd.certified_gap(best_cost,lbs)
            if REQUIRE_GLOBAL_CERTIFICATE and (
                    gap is None or gap > bnd.GLOBAL_REL_GAP):
                raise RuntimeError(
                    'WH1-DET: gemeinsamer 1%-Nachweis NICHT erreicht '
                    f'(best={best_cost:.4f} EUR/a, Gap={gap}, '
                    f'fehlende Schranken={sum(x is None for x in lbs)}). '
                    'Keine Uebernahme in Clusterbetrieb. '
                    f'Diagnose: {root/"vergleich.csv"}')
            if TEST_MAX_VARIANTS is not None:
                print('[WH1-BND] ACHTUNG: TEST_MAX_VARIANTS aktiv; '
                      'Zertifikat gilt nur fuer den gekuerzten Katalog!')
            ind['det_selected']=best
            if saved_sol is not None and saved_sol.is_file():
                shutil.copy2(saved_sol,
                             Path('optimization_results')/'solution_file_ehdo_model.txt')
            for row in rows:
                if row.get('status')=='optimal':
                    row['tac_equal_best_within_cent']=(
                        abs(float(row['ehdo_tac_EUR_a'])-best_cost)
                        <= TAC_TIE_ABS_EUR_A)
            equal_tac=[r['id'] for r in rows if r.get('tac_equal_best_within_cent')]
            best_result.update(
                industry_deterministic_variant_id=best.id,
                industry_deterministic_variant=best.summary(),
                industry_deterministic_variant_count=len(candidates),
                industry_deterministic_original_variant_count=total_before_dedup,
                industry_deterministic_skipped_duplicates=len(aliases),
                industry_deterministic_equal_tac_candidates=equal_tac,
                industry_deterministic_variants_unsolved=sum(
                    r.get('status') not in ('optimal','bound_pruned','infeasible_certified')
                    for r in rows),
                industry_deterministic_global_gap=float(gap) if gap is not None else None,
                industry_deterministic_global_gap_certified=(
                    gap is not None and gap <= bnd.GLOBAL_REL_GAP),
                industry_deterministic_comparison_file=str(root/'vergleich.csv'))
            print(f'[WH1-DET] Beste gefundene Variante: {best.id}; '
                  f'EHDO-TAC={best_cost:.2f} EUR/a; '
                  f'globaler nachgewiesener Gap={100*gap:.3f} %.')
            _write_report(root,rows,best.id,aliases,expected_count=len(candidates),
                          full_catalog=TEST_MAX_VARIANTS is None)
            return best_result
        except BaseException:
            ind.pop('det_selected',None)
            raise
    return _DetNamespace(**locals())
_runner = _init_runner()
del _init_runner

# Oeffentliche Schnittstelle fuer die bestehenden blauen Einhaengepunkte.
# Vollstaendige, isolierte Ursprungs-Namespaces fuer Diagnosen verfuegbar.
Input = _varianten.Input
Variant = _varianten.Variant
Point = _mehrquellen.Point
HXState = _physik.HXState
BoundContext = _bounds.BoundContext
CandidatePruned = _bounds.CandidatePruned
CandidateInfeasible = _bounds.CandidateInfeasible
CandidateUnresolved = _bounds.CandidateUnresolved
GLOBAL_REL_GAP = _bounds.GLOBAL_REL_GAP
SIZE_FACTORS = _varianten.SIZE_FACTORS
from_data = _varianten.from_data
generate = _varianten.generate
generate_single_sources = _varianten.generate_single_sources
generate_multi_source = _mehrquellen.generate_multi_source
deduplicate = _dubletten.deduplicate
monthly_plateau_audit = _varianten.monthly_plateau_audit
annuity = _varianten.annuity
bound_context = _bounds.bound_context
certified_gap = _bounds.certified_gap
execute = _bounds.execute
run_all = _runner.run_all
add_design = _pyomo.add_design
add_operation = _pyomo.add_operation
design_result = _pyomo.design_result
operating_result = _pyomo.operating_result

