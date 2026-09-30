# Automated OSM district discovery and building-use analysis for StädteRegion Aachen

## How to read this document

This document distinguishes the implemented procedure from methodological
decisions that still require validation.



All equations are displayed in mathematical notation. Distances and areas are
calculated in metres and square metres unless stated otherwise.

## 1. Objective and analytical unit

The objective is to identify spatially coherent non-industrial candidate districts in
StädteRegion Aachen and to calculate, for each candidate:

1. settlement-morphology indicators;
2. an automated settlement-type assignment with a recorded assignment reason;
3. shares of residential, mixed-use, non-residential and unknown-use buildings;
4. conditional shares of individual non-residential building (NRB) types.

The analytical unit is a **candidate district** defined first by road-block or
street-network continuity and exceptional building gaps. Complete natural
components containing 10--70 eligible building footprints are retained. The
target of 40 buildings is used only as a preference when an oversized street
component must be divided or an undersized road block must be merged. A
candidate is not an administrative district and its settlement-type label is
not treated as a validated observation.

The implemented workflow is:

1. obtain the administrative study boundary and OSM features;
2. construct the eligible building population and the clustering road network;
3. construct closed road blocks and retain complete blocks with 10--70
   buildings, merging only blocks that are too small;
4. associate the remaining buildings with streets and form connected,
   two-sided street clusters;
5. apply the common point- and footprint-based boundary procedure and replace
   the final boundary of clearly rural candidates by building influence cells;
6. divide a candidate when a spatially separate row-structured subarea and
   a contrasting non-row subarea can both form valid candidates;
7. calculate morphology and assign preliminary types;
8. classify building uses and aggregate the required ratios.



## 2. Data, coordinate systems and reproducibility

### 2.1 Study region and OSM features

The study region is the OSM administrative boundary of StädteRegion Aachen,
North Rhine-Westphalia, Germany. Data are obtained through OSMnx and Overpass.
The query retains objects carrying any of the following attributes: `building`,
`building:use`, `building:flats`, `highway`, `shop`, `amenity`, `office`,
`craft`, `landuse`, `leisure`, `tourism`, `healthcare`, `industrial` and
`sport`, `man_made`, `railway` and `public_transport`. The cached source contains 389,080 OSM features. A source cache created
before `building:use` and `building:flats` were added to the query must be
refreshed before these attributes can affect the results. The same applies to
the additional factory and transport attributes when absent from a source cache.

All metric geometric operations are performed in ETRS89 / UTM zone 32N
(EPSG:25832). Map outputs are transformed to WGS 84 (EPSG:4326).

### 2.2 Parameter workbook and random seed

To refresh the source dataset, open `examples/refresh_aachen_osm_data.py` and
click Run. This downloads source data only. The existing source files are copied
to a dated `cache_backups` directory before the replacement is installed. The
shared source directory remains `examples/results/aachen_osm_pilot_v2`, which
ordinary quick and full analysis runs reuse without downloading again.
`download.json` records the retrieval date, query tags, retained columns and
nonempty tag counts. Keep this dataset fixed during method comparisons.
Refresh only when additional source attributes or a newer OSM snapshot are
deliberately required. The pilot's explicit `--download` option also forces a
refresh of this shared cache, then continues with analysis.

The first worksheet of `typdistrict_parameters.xlsx` supplies the minimum and
maximum BCR, building-density and FAR values for source settlement types A–I.
The workbook is opened read-only. Its SHA-256 hash is recorded before and after
the run:

**7d7c4a0aa0bc358b84f7429545015f7b0676a83f1d244f0c8cabc877d05fc05a**

The two hashes are identical. Random ordering of road seeds uses seed 2026,
making a run reproducible when the data, code and software versions remain
unchanged.



### 2.3 Full and quick-test run modes

An interactive run without a `--scope` argument asks whether to process:

1. a quick-test area within the configured radius of central Aachen
   (currently 7 km); or
2. the complete StädteRegion Aachen.

Pressing Enter selects the quick test. The equivalent command-line arguments
are `--scope quick` and `--scope full`. The quick-test source features are
spatially filtered before reprojection, candidate construction, indicator
calculation and map generation. This substantially reduces development time.
Its results are written to
`examples/results/aachen_osm_building_sections_compact_v7_quick`, while the
full run uses `examples/results/aachen_osm_building_sections_compact_v7`.
Consequently, testing cannot overwrite the complete regional results.

The selected scope, quick-test centre, radius and retained source-feature count
are recorded in the manifest. The review map automatically fits its initial
view to the generated candidates.



## 3. Eligible buildings and roads

### 3.1 Eligible building footprints

An OSM object enters the building population when it:

- has polygon or multipolygon geometry;
- has a non-empty `building` tag;
- has an interior representative point inside the study boundary; and
- is not tagged as `garage`, `garages`, `shed`, `roof`, `carport`, `greenhouse`,
  `construction`, `ruins` or `no`.

After duplicate removal, footprints smaller than $20\,\mathrm{m}^2$ are
excluded before roads, blocks, candidate membership and morphology indicators
are constructed. A footprint of exactly $20\,\mathrm{m}^2$ remains eligible.
The number removed by this rule is recorded in the manifest and run report.

Generic `building=yes` footprints are retained. Their use may be unknown, but
excluding them would distort building count, density and coverage.

Exact duplicate geometries are removed. A smaller polygon is also removed when
more than 98% of its area is covered by a polygon whose area is more than 1%
larger. This is intended to remove duplicate OSM way/relation representations.
The run-specific footprint count is recorded in the manifest and inserted into
the generated result section of this document.



### 3.2 Industrial-site exclusion

Complete industrial sites are excluded spatially before candidate construction.
For every OSM polygon $I_k$ explicitly tagged `landuse=industrial`, the
industrial exclusion mask is

$$
\Omega_{\mathrm{industrial}}=
\bigcup_k I_k.
$$

The effective analysis region is

$$
\Omega_{\mathrm{analysis}}=
\Omega_{\mathrm{study}}\setminus
\Omega_{\mathrm{industrial}}.
$$

An otherwise eligible building is removed when any part of its complete
footprint intersects $\Omega_{\mathrm{industrial}}$. This intentionally
excludes every building located on an industrial site, irrespective of its
individual building or use tag. Road geometries are cut at the mask boundary,
so street and block candidates cannot grow through an industrial site. Every
candidate envelope is clipped to $\Omega_{\mathrm{analysis}}$ and therefore
cannot cover the excluded land.

No additional buffer is placed around the OSM industrial polygon, and other
land-use categories such as `commercial` and `retail` are not included in this
mask. The number of source polygons, their union area, and the number of removed
otherwise eligible buildings are recorded in the manifest and run report. The
source polygons are exported to `industrial_exclusion_sites.geojson` and shown
as an optional red layer in the review map.

This scope decision also applies to the use analysis. Consequently, the
reported residential, mixed-use, non-residential and NRB shares describe
**non-industrial settlement areas** and must not be interpreted as shares for
the complete regional building stock.



### 3.3 Roads used for clustering

Road features are initially retained for the following OSM highway classes:

- primary, secondary and tertiary;
- unclassified and residential;
- living street;
- service and pedestrian.

Pedestrian geometries are excluded from the street-clustering graph. Service
roads are included unless their OSM `service` subtype is explicitly
`driveway`, `parking_aisle` or `drive-through`. A `highway=service` road with no
such subtype, or with another subtype, can therefore connect buildings during
street-candidate construction. The excluded subtypes remain available in the
source data but do not form clustering edges. Road-block polygonization uses
ordinary roads and excludes service and pedestrian roads so that small access
roads do not create artificial closed blocks.

The OSM `service` column must be present in the source cache to apply this
selection safely. When a legacy slim cache lacks that column, all service roads
remain excluded and the run prints a notice. Refreshing the OSM source cache
activates the selective service-road rule.



## 4. Construction of candidate districts

Candidate membership is generated in two consecutive stages. Complete closed
road blocks are considered first. Connected street growth is then applied to
the buildings that remain unassigned. Both stages use the common boundary
procedure in Section 4.5. After their boundaries have been finalized, a separate
step searches the remaining buildings for additional scattered type-A candidates
(Section 4.9).

### 4.1 Closed road-block candidates

All ordinary retained road geometries, excluding service and pedestrian roads,
are geometrically united with the study-region boundary and polygonized. Each
resulting polygon represents a closed road block.
A building belongs to a block when its interior representative point lies
inside that polygon.

Blocks are processed in an order randomized with seed 2026. An individual
block containing 10--70 eligible buildings provides a preliminary candidate
without being enlarged toward the target of 40. Only a block containing fewer
than 10 buildings is combined with directly adjacent blocks while the total
remains at most 70. Two blocks are adjacent only when they share more than 1 m
of boundary. From all admissible neighbours, the block that brings the combined
building count closest to 40 is selected; ties are resolved by block area and
then by block index. The value 40 therefore guides a required merge but does
not determine the boundary of an already admissible complete block.

Let $S$ be the current connected set of blocks, $B(S)$ its buildings and
$\mathcal A(S)$ its unused adjacent blocks. The next block is

$$
b^*=\underset{b\in\mathcal A(S)}{\operatorname{argmin}}
\left|40-\left|B(S\cup\{b\})\right|\right|,
$$

subject to

$$
\left|B(S\cup\{b\})\right|\leq70.
$$

Before a preliminary block candidate is accepted, a spatial-coherence check is
applied to its building representative points. For each selected building, the
distance to its nearest selected neighbour is calculated. When at least five
distances are available, the candidate-specific exceptional-gap threshold
$g_{\mathrm{break}}$ is calculated using the same
$Q_3+3\,\mathrm{IQR}$ rule and zero-IQR fallback defined in Section 4.3.
Buildings are then connected when their representative-point distance does not
exceed $g_{\mathrm{break}}$, and the connected components of this proximity
graph are determined.

If the largest component contains at least 10 buildings and all remaining
components together contain at most four buildings, the small remote
components are removed. Otherwise, the preliminary membership is retained
unchanged. The final district boundary is subsequently reconstructed from the
retained buildings using Section 4.5. This prevents one or a few buildings in
the distant end of a large OSM road polygon from stretching an otherwise
coherent block candidate over a long empty corridor.

Empty blocks, individual blocks containing more than 70 buildings and block
groups covering more than $4\,\mathrm{km}^2$ are not used for block-based
membership. A group is accepted only when its closed membership after the
common boundary procedure contains 10--70 buildings and its final envelope
does not intersect an accepted candidate. The block geometry therefore
determines preliminary membership but is not used directly as the final
district boundary.

All buildings belonging to accepted block candidates are marked as assigned.
Every other building remains available to the street-growth stage.



### 4.2 Noding and assignment of remaining buildings to roads

All retained clustering roads are geometrically united. Intersections become
network nodes, and the lines between nodes become graph edges. Two edges are
treated as adjacent when their end coordinates are equal after rounding to one
decimal place, corresponding to an endpoint tolerance of approximately
0.1 m.

For each building $i$, an interior representative point $\mathbf{p}_i$ is
created. Its nearest noded clustering road $e_i^*$ is identified by

$$
e_i^*=\underset{e\in\mathcal{E}}{\operatorname{argmin}}
\;d(\mathbf{p}_i,e).
$$

The building is assigned to that road only if

$$
d(\mathbf{p}_i,e_i^*)\leq150\ \mathrm{m}.
$$

The assignment does not distinguish the left and right sides of the road.
Buildings on both sides are therefore associated with the same noded road.



### 4.3 Building-defined street sections

The position of each associated building is projected onto its noded road. Let
$s_i$ denote the distance of this projected position from the start of the road.
Positions equal after rounding to 0.1 m are treated as one street station. This
allows buildings with the same along-road position on opposite sides to enter
the same station without introducing a physical section length.

To keep the regional graph computationally tractable, consecutive stations are
combined until adding another station would exceed

$$
N_{\mathrm{section}}^{\max}
=\left\lceil\frac{N_{\mathrm{target}}}{10}\right\rceil
=4
$$

buildings, where $N_{\mathrm{target}}=40$. A single station can exceptionally
contain more than four buildings when several projected positions coincide.
This rule guarantees approximately ten or more clustering units for a
target-sized candidate while avoiding a fixed length in metres.

For two consecutive station groups $G_k$ and $G_{k+1}$, the section boundary is
placed at

$$
b_{k+\frac12}=
\frac{\max_{i\in G_k}s_i+\min_{i\in G_{k+1}}s_i}{2}.
$$

Before the station groups are constructed, consecutive projected building
positions are checked for exceptional empty gaps. Let

$$
g_r=s_{r+1}-s_r
$$

denote the gap between two consecutive stations on the same noded road. If at
least five gaps are available, their first and third quartiles are used to
calculate

$$
\mathrm{IQR}_g=Q_{3,g}-Q_{1,g},
\qquad
g_{\mathrm{break}}=Q_{3,g}+3\,\mathrm{IQR}_g.
$$

When $\mathrm{IQR}_g$ is numerically zero, the fallback threshold is

$$
g_{\mathrm{break}}=3\widetilde g,
$$

where $\widetilde g$ is the median gap. A gap larger than
$g_{\mathrm{break}}$ interrupts road continuity for clustering. The empty road
interval between the two stations is omitted from the clustering graph, so a
street candidate cannot grow across it. With fewer than five gaps, no
statistical break is introduced at this stage.

The first and last sections extend to the endpoints of the noded road. Dense
frontages consequently create short sections, whereas sparse frontages create
long sections. No universal maximum road-section length is imposed.



### 4.4 Natural street components and division of oversized components

Only buildings not assigned through the road-block stage can enter a street
candidate. After exceptional gaps have interrupted road continuity, all
occupied street sections that remain connected through shared road endpoints
form a natural street component. Building count is evaluated only after these
components have been identified.

A complete natural component is accepted without division when

$$
10\leq |B(S)|\leq70.
$$

Components with fewer than 10 buildings do not enter the accepted candidate
set. A component containing more than 70 buildings is divided. The preferred
partition size is

$$
N_{\mathrm{target}}=40
$$

used as a preferred partition size. Occupied sections are placed in an order
randomized with seed 2026. Starting from the first available section, connected
sections are added until the preferred partition size is reached or no
admissible connected section remains. From the connected frontier, the next
section minimizes

$$
c_e=\frac{L_e}{N_e^{\mathrm{new}}},
$$

where $L_e$ is the added section length and $N_e^{\mathrm{new}}$ is the number
of buildings newly added by it. Ties are resolved by closeness to 40, by the
larger number of added buildings, by seed order and finally by section index.
After one partition is removed, every remaining connected component is assessed
again using the same rules. Consequently, an undivided 23-building component
is retained as 23 buildings, whereas an 80-building component can be divided
into two partitions close to 40 buildings when its graph structure permits.

After growth, small terminal branches are checked before boundary construction.
A selected edge is terminal when it has at most one neighbour inside the
selected cluster. A terminal edge can be removed only when it contains at most
four selected buildings and at least 10 buildings remain in the core. For the
current candidate, the nearest-neighbour distances between all building
representative points are used to calculate an exceptional-gap threshold with
the same $Q_3+3\,\mathrm{IQR}$ rule and zero-IQR fallback defined above. Let
$B_e$ be the buildings on terminal edge $e$ and $B_{\mathrm{core}}$ the
remaining buildings. The terminal connection gap is

$$
g_e^{\mathrm{terminal}}=
\min_{i\in B_e,\,j\in B_{\mathrm{core}}}
d(\mathbf p_i,\mathbf p_j).
$$

The terminal edge is removed when
$g_e^{\mathrm{terminal}}>g_{\mathrm{break}}$. The check is repeated because
removing one tail can expose another terminal edge. The district boundary is
then constructed anew from the retained building set using the procedure in
Section 4.5.

A building already contained in an accepted candidate cannot be used again.
The street graph is separated into natural components and partitioned without
reusing sections. Adjacent road sections that do not belong to an accepted
candidate remain available for other candidates.



### 4.5 Point-based membership closure and footprint-based final boundary

A connected block group or street cluster supplies a preliminary building set.
Boundary construction then separates the membership decision from the
representation of the final physical district extent:

1. Create one interior representative point for every initially selected
   building.
2. Calculate the median nearest-neighbour distance between the selected
   building points and derive an adaptive hull ratio between 0.30 and 1.00.
   Construct the point hull using this ratio and without internal holes.
3. Calculate the clear distance from every selected footprint to its nearest
   other selected footprint and derive the adaptive margin.
4. Buffer the point-based hull using this margin and clip it to the study-region
   boundary. This is the preliminary membership envelope.
5. Add every eligible building whose interior representative point lies inside
   the preliminary envelope and repeat the procedure until membership is stable.
6. Apply the mandatory building-point-based spatial-coherence check. Split membership
   at exceptional spatial bridges and discard every resulting component with
   fewer than 10 buildings.
7. Construct the final hull separately from the complete footprints of every
   retained coherent component and apply the same adaptive margin.
8. Locally constrain the final margin wherever it approaches an eligible
   building that is not assigned to the candidate.
9. Fill every completely enclosed interior area that contains no unassigned
   eligible building footprint.
10. Close narrow boundary bays that are open on one side. When a bay intersects
   an eligible building that is still available, add that building to the
   candidate and reconstruct the boundary. Do not close a bay across a building
   already assigned elsewhere or deliberately excluded from this candidate.

Let $\widetilde d_{\mathrm{gap}}$ be the median clear nearest-footprint gap.
The implemented margin is

$$
m=\min\!\left(30\ \mathrm{m},
\max\!\left(5\ \mathrm{m},
\frac{\widetilde d_{\mathrm{gap}}}{2}\right)\right).
$$

Let $\widetilde d_{\mathrm{nn}}$ denote the median nearest-neighbour distance
between the selected building points. The adaptive concave-hull ratio is

$$
r_{\mathrm{hull}}=
0.30+0.70\,
\operatorname{clip}\!\left(
\frac{\widetilde d_{\mathrm{nn}}-20\ \mathrm{m}}
{55\ \mathrm{m}-20\ \mathrm{m}},0,1
\right).
$$

Groups with a median nearest-neighbour distance no greater than 20 m therefore
use $r_{\mathrm{hull}}=0.30$. The ratio increases continuously for more widely
spaced groups and reaches 1.00, corresponding to the convex hull, at 55 m.
This retains more of the open land between spatially sparse buildings instead
of wrapping the boundary tightly around individual road branches.

The preliminary membership envelope is

$$
\Omega_{\mathrm{pre}}=
\operatorname{buffer}\!\left(
\operatorname{concaveHull}_{r_{\mathrm{hull}}}
\left(\{\mathbf p_i:i\in B\}\right),m
\right)
\cap\Omega_{\mathrm{study}},
$$

where $\mathbf p_i$ is the interior representative point of building $i$,
$B$ is the current building set and $\Omega_{\mathrm{study}}$ is the study
boundary.

Membership is then closed iteratively. Every eligible building whose interior
representative point lies inside $\Omega_{\mathrm{pre}}$ is added to $B$,
after which the preliminary envelope is recalculated. The membership is stable
when no further building is added. At most ten closure iterations are
attempted.

After membership has stabilized, a final spatial-coherence check is applied
before any physical district boundary is constructed. A Euclidean minimum
spanning tree $T(B)$ is calculated for the interior representative point of
each building. Its
$N_b-1$ edge lengths are denoted by $\ell_e$. The candidate-specific exceptional
bridge threshold is

$$
\ell_{\mathrm{break}}=Q_3(\ell_e)+3\,
\operatorname{IQR}(\ell_e).
$$

When the interquartile range is numerically zero, the implemented fallback is

$$
\ell_{\mathrm{break}}=3\,
\operatorname{median}(\ell_e).
$$

Every tree edge satisfying

$$
\ell_e>\ell_{\mathrm{break}}
$$

is removed. The remaining connected components represent spatially coherent
building groups. Each component containing 10--70 buildings is reconstructed
as an independent candidate. Components containing fewer than 10 buildings are
discarded and cannot be added again during the reconstruction. If all resulting
components contain fewer than 10 buildings, the complete original candidate is
rejected. Thus, two small groups connected only by a long empty corridor are
not accepted as one district.

After this validation, the complete assigned footprints $P_i$ of each retained
component are used to construct its buffered physical envelope

$$
\Omega_{\mathrm{buf}}=
\operatorname{buffer}\!\left(
\operatorname{concaveHull}_{r_{\mathrm{hull}}}
\left(\bigcup_{i\in B}P_i\right),m
\right)
\cap\Omega_{\mathrm{study}}.
$$

The margin is not allowed to cover another eligible building footprint. For
each unassigned building $j$ near the buffered envelope, its clear distance to
the assigned footprints is

$$
g_j=d\!\left(P_j,\bigcup_{i\in B}P_i\right).
$$

An exclusion zone is formed by buffering the external footprint by half this
distance,

$$
Z_j=\operatorname{buffer}\!\left(P_j,\frac{g_j}{2}\right),
$$

and the final envelope is

$$
\Omega_{\mathrm{final}}=
\Omega_{\mathrm{buf}}\setminus\bigcup_{j\notin B}Z_j.
$$

Consequently, the intended 5--30 m margin is retained where sufficient space
is available, but it is locally reduced to approximately the midpoint between
an assigned and an unassigned building. This geometric constraint does not add
the external building to the candidate; membership remains determined by the
representative-point rule.

After applying the external-building constraint, interior rings are examined.
An enclosed area is filled and treated as part of the district when no
unassigned eligible building footprint intersects it. A hole is retained when
it contains such a footprint. This prevents an empty courtyard, green space or
similar area that is surrounded on all sides by the district from being
excluded, while preserving the rule that the district envelope must not cover
another eligible building.

Completely enclosed holes do not include narrow open spaces that are surrounded
by the candidate on three sides but remain connected to the exterior. These
boundary bays are treated with a morphological closing. Let
$\Omega_{\mathrm{hole}}$ denote the envelope after the preceding hole test and
let $\widetilde d_{\mathrm{nn}}$ be the median nearest-neighbour distance of
the assigned building points. The closing radius is

$$
r_{\mathrm{bay}}=
\min\!\left(30\ \mathrm{m},
\max\!\left(m,1.25\,\widetilde d_{\mathrm{nn}}\right)\right).
$$

The lower bound $m$ prevents the bay rule from being weaker than the ordinary
envelope margin, while the upper bound of 30 m prevents unrestricted expansion.
The provisional closed geometry is

$$
\Omega_{\mathrm{close}}=
\operatorname{buffer}\!\left(
\operatorname{buffer}\!\left(
\Omega_{\mathrm{hole}},r_{\mathrm{bay}}\right),-r_{\mathrm{bay}}
\right).
$$

The possible additions are the connected components $C_k$ of

$$
\Omega_{\mathrm{close}}\setminus\Omega_{\mathrm{hole}}.
$$

For each component $C_k$, every eligible footprint intersecting the possible
addition is identified. A component containing no outside building is added
directly. If it intersects one or more still-unassigned buildings, these
buildings are added to $B$ and the complete membership and boundary procedure
is repeated. The component is rejected when it intersects a building already
assigned to another candidate, a building excluded during spatial-coherence
splitting, or when absorption would increase the candidate above 70 buildings.

This rule therefore handles two cases. An empty three-sided indentation becomes
part of the district area. An indentation containing an available footprint
also becomes part of the district, and that complete building becomes a member
rather than being geometrically covered but omitted. Including the additional
land generally reduces BCR and density; absorbing a building simultaneously
increases the numerator of BCR and the building count. The final effect is
therefore calculated from the reconstructed candidate rather than assumed.

A candidate is rejected if:

- its closed membership falls outside 10–70 buildings;
- it contains a building already assigned elsewhere;
- the envelope is empty; or
- its envelope intersects any accepted candidate envelope.





### 4.6 Separate rural influence boundary

The preceding procedure determines candidate membership and provides the final
boundary for candidates in developed surroundings. It can nevertheless
underestimate rural district area because its ordinary outer margin is limited
to 30 m. Open land associated with spatially separated rural buildings would
then be omitted, causing BCR and building density to be overestimated.

The rural boundary is applied only when the original 500 m context ring has

$$
\rho_{\mathrm{context}}<10\ \mathrm{buildings\,ha^{-1}}
\quad\text{and}\quad
\mathrm{BCR}_{\mathrm{context}}<0.10.
$$

This strict condition controls only the use of the rural boundary; the final
rural/urban context used for type matching is described separately in Section
6.

One interior representative point is constructed for every eligible building
in the complete analysis region. These points generate a Voronoi partition. If
$V_i$ is the Voronoi cell of building $i$, every location inside $V_i$ is
closer to building $i$ than to any other eligible building. The boundary
between two cells is consequently located halfway between their building
points.

For a clearly rural candidate with member set $B$, the preliminary building
influence area is

$$
\Omega_{V}=\bigcup_{i\in B}V_i.
$$

This alone can become unrealistically large when the nearest outside building
is far away. The method therefore limits the influence area using the local
spacing of the candidate's own building points. Let $d_i^{\mathrm{nn},B}$ be
the distance from member point $i$ to its nearest other member point. The
candidate-specific reach is

$$
d_{\mathrm{lim}}=
Q_3\!\left(d^{\mathrm{nn},B}\right)
+1.5\,\operatorname{IQR}\!\left(d^{\mathrm{nn},B}\right).
$$

If the interquartile range is numerically zero, the fallback is
$d_{\mathrm{lim}}=1.5\operatorname{median}(d^{\mathrm{nn},B})$. Let $H_B$ be
the adaptive concave hull of the complete selected building footprints. The
final rural boundary is

$$
\Omega_{\mathrm{rural}}=
\Omega_V
\cap\operatorname{buffer}(H_B,d_{\mathrm{lim}})
\cap\Omega_{\mathrm{analysis}}.
$$

Here, $\Omega_{\mathrm{analysis}}$ is already reduced by the industrial-site
mask. The resulting rural boundary therefore:

- retains the open land whose nearest eligible building belongs to the
  candidate;
- stops halfway toward every neighbouring unselected eligible building;
- cannot extend farther from the candidate's building structure than the
  locally derived reach $d_{\mathrm{lim}}$;
- stops at excluded industrial land and at the study-region boundary; and
- follows the natural candidate separations already created at exceptional
  building gaps during clustering.

The building membership itself is not changed. Existing non-rural candidate
envelopes are retained as obstacles. Because a complete external footprint can
cross the Voronoi boundary defined by building points, every intersecting
external footprint is removed from the influence geometry before the selected
member footprints are explicitly restored. This prevents meaningful overlaps
between neighbouring candidate envelopes while ensuring that every member
footprint remains inside its own district. BCR, building density and FAR are
subsequently calculated using $\Omega_{\mathrm{rural}}$.



### 4.7 Morphological separation of row and non-row subareas

The preceding construction follows roads and spatial continuity. A connected
candidate can nevertheless contain two visibly different parts, for example a
regular row estate beside an irregular commercial or residential
area. Treating the complete geometry as one district can hide the row structure
and incorrectly favour another settlement type.

The general row detector described in Section 5 marks every building
that belongs to a qualified row. For candidate building $i$, let $z_i=1$ denote
row membership and $z_i=0$ denote non-row membership. The building points are
projected onto the first principal spatial axis. Possible cut positions are
tested only when both resulting parts contain at least 10 buildings.

For a possible cut $c$, let $L_c$ and $R_c$ be the buildings on its two sides.
The row-share contrast is

$$
\Delta s_c=
\left|
\frac{\sum_{i\in L_c}z_i}{|L_c|}-
\frac{\sum_{i\in R_c}z_i}{|R_c|}
\right|,
$$

and the best separation accuracy is

$$
a_c=\frac{1}{N_b}\max\!\left(
\sum_{i\in L_c}z_i+\sum_{i\in R_c}(1-z_i),
\sum_{i\in L_c}(1-z_i)+\sum_{i\in R_c}z_i
\right).
$$

The cut is eligible only if $a_c\geq0.70$, $\Delta s_c\geq0.40$, and the
projected building-point gap at the cut is statistically exceptional:

$$
g_c>Q_3(g)+1.5\,\operatorname{IQR}(g).
$$

When the interquartile range is numerically zero, the fallback threshold is
$3\operatorname{median}(g)$. The dividing line is placed halfway across the
exceptional gap and must not intersect any selected footprint. When several
cuts qualify, the procedure prefers the highest accuracy, then the greatest
row-share contrast, and then the largest gap. The existing candidate polygon is
split by that line; its land is partitioned between the two outputs without
creating or deleting area. Each output receives only the buildings on its side
of the cut. The row-dominated output is marked `morphology_row_split`, and the
contrasting output is marked `morphology_nonrow_split`.

Both outputs are classified independently by the ordinary scoring rules in
Section 6. Row structure supports both E and F and therefore does not assign a
type by itself. Their distinction is instead determined by the complete set of
available indicators and eligibility rules, especially the conditional
residential SFH/MFH requirement when sufficient OSM typology information is
available.



### 4.8 Separation from other candidates

Accepted candidate polygons are stored in a spatial index. Any newly generated
candidate whose polygon intersects an accepted polygon is rejected. Buildings
already assigned to an accepted candidate are unavailable to every subsequent
candidate. These two checks enforce unique building membership and prevent
accepted candidate envelopes from overlapping. No additional fixed-distance
exclusion zone is applied around an accepted envelope.



### 4.9 Additional scattered settlements from unassigned buildings

After the existing candidates and their rural boundaries have been finalized,
an additional pass searches unused buildings for scattered settlements. Existing
district membership, geometry, identifiers and type comparisons are preserved.

Building representative points are associated with the nearest retained noded
road within 150 m. Their projected positions form street stations, rounded to
0.1 m. Buildings at the same station are grouped together. Stations containing
an already assigned building act as barriers. Starting from each unused
station, the algorithm follows the road network through empty road sections
until it reaches another occupied station. The shortest road distance connects
these neighbouring stations. This allows a sparse sequence to continue across
empty road sections and intersections.

Exceptional gaps are removed before grouping. For each station, the local
sample consists of nearest-station road distances for itself and stations up
to two connections away. With at least five positive distances, the limit is
$Q_3+3\,\mathrm{IQR}$; the zero-IQR fallback is three times the median. With
fewer than five distances, three times the median is used. A connection must
not exceed either endpoint's limit. This permits larger gaps where the local
spacing is consistently large, while interrupting an exceptional empty stretch
between compact groups.

Connected groups containing 10–70 buildings proceed to boundary construction.
Larger groups are divided recursively at the longest edge of their minimum
spanning tree, using road distance as the edge weight. Groups below ten
buildings are discarded. There is no 40-building target in this pass.

The common membership-closure and spatial-coherence procedure in Section 4.5
is applied. A proposal proceeds only if its surrounding density is below
10 buildings/ha and its surrounding BCR is below 0.10. The rural influence
boundary from Section 4.6 is then applied, treating all existing envelopes as
fixed obstacles. The final envelope must not intersect an accepted district
or reuse any assigned building.

The completed proposal is evaluated against the existing type-A requirements,
including spacing, attachment, frontage, context and row participation. Its
type-A total range score must also be at most 1. A passing proposal is appended
as an additional A district; a failing proposal is not added. Other types are
not competing assignments in this targeted pass. The boundary-method field
starts with `additional_scattered_A`, making this origin identifiable in the
map and exported results. Explicitly targeted A sampling changes the sample's
composition; counts are not estimates of regional settlement-type prevalence.

These candidates contribute to aggregate results, while candidates accepted
before this pass retain their original memberships and assignments.

## 5. Morphological indicators

### 5.1 Indicators used for preliminary type matching

For candidate envelope $\Omega$, let $A_{\mathrm{district}}$ be its area,
$N_b$ its number of buildings and $A_{\mathrm{fp},i}$ the footprint area of
building $i$. The building coverage ratio is

$$
\mathrm{BCR}=
\frac{\displaystyle\sum_{i=1}^{N_b}A_{\mathrm{fp},i}}
{A_{\mathrm{district}}}.
$$

Building density in buildings per hectare is

$$
\rho_b=
\frac{10^4N_b}{A_{\mathrm{district}}}.
$$

An OSM `building:levels` value is treated as valid when it is greater than zero
and no greater than 100. Let $N_{\mathrm{levels}}$ be the number of buildings
with a valid value. Storey-data coverage is

$$
c_{\mathrm{levels}}=
\frac{N_{\mathrm{levels}}}{N_b}.
$$

FAR is calculated only when

$$
c_{\mathrm{levels}}\geq0.66.
$$

Missing values in such a candidate are replaced by the arithmetic mean
$\overline n_f$ of the observed values. Defining

$$
n_{f,i}^{*}=
\begin{cases}
n_{f,i}, & \text{if a valid value is available},\\
\overline n_f, & \text{otherwise},
\end{cases}
$$

the estimated FAR is

$$
\mathrm{FAR}=
\frac{\displaystyle\sum_{i=1}^{N_b}
A_{\mathrm{fp},i}n_{f,i}^{*}}
{A_{\mathrm{district}}}.
$$

The fourth active matching indicator describes the typical distance between
neighbouring building centre points. Its preferred form is the longitudinal
distance between consecutive building centroids on the same side of the same
road. Service and pedestrian roads are excluded, and the remaining roads are
noded at geometric intersections. Each building centroid $\mathbf c_i$ is
assigned to its nearest noded road $e_i$ when the centroid-to-road distance does
not exceed 150 m. Its projected position along that road is

$$
s_i=\operatorname{project}(\mathbf c_i,e_i).
$$

The local road direction and the sign of the corresponding cross product are
used to distinguish the two road sides. Projected positions are grouped by road
and side and sorted. For two consecutive positions in a group, the longitudinal
spacing is

$$
\Delta s_k=s_{(k+1)}-s_{(k)}.
$$

Buildings on opposite sides of a road therefore do not form a spacing pair.
When at least one valid same-road-side pair exists, the candidate-level
indicator is the median of all $K$ valid spacings:

$$
\widetilde d_{\mathrm{road}}=
\operatorname{median}\left(\Delta s_1,\ldots,\Delta s_K\right).
$$

If no valid same-road-side pair exists, the indicator falls back to the
two-dimensional distance from each building centroid to its nearest other
building centroid. For building $i$, this distance is

$$
d_i^{\mathrm{nn}}=\min_{j\ne i}\left\|\mathbf c_i-\mathbf c_j\right\|,
$$

and the fallback candidate value is

$$
\widetilde d_{\mathrm{nn}}=
\operatorname{median}\left(d_1^{\mathrm{nn}},\ldots,d_{N_b}^{\mathrm{nn}}\right).
$$

The exported field `building_spacing_source` records whether the active value
comes from `same_road_side` or `nearest_neighbour_fallback`. Minimum, maximum,
mean, median, first-quartile and third-quartile same-road-side values, the
interquartile range, the maximum-to-median ratio and the number $K$ of valid
pairs remain available for review. For settlement type $t$, the active spacing
value $\widetilde d$ is compared with the workbook interval

$$
d_{t}^{\min}\leq\widetilde d\leq d_{t}^{\max},
$$

defined by the columns `Min Abstand benachbarter Hausanschlüsse (m)` and
`Max Abstand benachbarter Hausanschlüsse (m)`. Although the source columns
refer to neighbouring house connections, the district-generation code uses
these values to control the longitudinal placement of building centre points
along roads. The road-side centroid-spacing definition therefore reproduces
the geometric interpretation used by the generator more closely than an
unrestricted two-dimensional nearest-neighbour distance. The latter is used
only to avoid losing the indicator when the road-side construction produces no
valid pair.



The next active matching indicator describes the attachment structure. A building is
marked as attached if more than 1 m of its footprint boundary is shared with
another selected footprint. With indicator $I_i^{\mathrm{att}}$, the attached
building percentage is

$$
s_{\mathrm{att}}=
\frac{100}{N_b}\sum_{i=1}^{N_b}I_i^{\mathrm{att}}.
$$

The source workbook does not contain type-specific attachment ranges. A simple
binary modelling assumption is therefore used. Row-housing, row-development,
block-development and city-centre types E, F, H and I are treated as
attachment-based settlement
types and require

$$
s_{\mathrm{att}}\geq50\,\%.
$$

Types A--D and G use the complementary range
$0\,\%\leq s_{\mathrm{att}}\leq50\,\%$, except for scattered-settlement type
A, for which the stricter range
$0\,\%\leq s_{\mathrm{att}}\leq35\,\%$ is used. At exactly 50%, the
attachment-based types and the non-attachment-based types other than A satisfy
their intervals, so the other indicators determine whether a unique type
remains. The attached-building percentage therefore enters the preliminary
type-matching calculation.


An additional conditional indicator represents residential building typology.
The workbook EFH/MFH percentages refer only to residential buildings, not to
all buildings in a candidate. Evidence is evaluated in the following fixed
order, and a decision from an earlier source is not overwritten by a later one:

1. `building:flats=1` is SFH-like, while `building:flats>=2` is MFH-like;
2. a specific `building:use` value is evaluated;
3. the main `building` value is evaluated; and
4. footprint area is used only for a still-ambiguous residential footprint.

The specific `building:use` and `building` values are mapped as follows:

- SFH-like: `house`, `detached`, `semidetached_house`, `terrace`, `bungalow`
  and `farm`;
- MFH-like: `apartments` and `dormitory`;
- residential but typologically ambiguous: `residential`.

Invalid or missing `building:flats` values provide no typology evidence. A
specific non-residential `building:use` prevents a residential-looking main
building tag from entering the residential-typology population. For a
residential footprint that remains ambiguous after the explicit evidence has
been evaluated, a conservative area-based inference is applied:

$$
\text{inferred type}_i=
\begin{cases}
\mathrm{SFH\text{-}like}, & A_i<120\,\mathrm{m}^2,\\
\mathrm{unknown}, & 120\,\mathrm{m}^2\leq A_i\leq220\,\mathrm{m}^2,\\
\mathrm{MFH\text{-}like}, & A_i>220\,\mathrm{m}^2.
\end{cases}
$$

In the available explicitly tagged Aachen sample, approximately 79% of
residential footprints below $120\,\mathrm{m}^2$ were SFH-like and approximately
80% above $220\,\mathrm{m}^2$ were MFH-like. The upper rule identifies a
comparatively reliable subset but captures only approximately 22% of all
explicitly tagged MFH-like buildings.

Generic `building=yes` objects and explicitly non-residential buildings do not
enter the residential-typology population. They remain fully included in
building count, area, BCR, density, spacing, attachment and district-boundary
calculations.

An OSM `building=terrace` polygon may describe a complete terrace rather than
one dwelling. It is therefore counted once as one SFH-like footprint. The
number of such aggregate terrace footprints is exported separately; the method
does not invent a dwelling count when the OSM geometry does not supply one.

Let $N_{\mathrm{SFH}}$ and $N_{\mathrm{MFH}}$ include both explicitly tagged and
area-inferred residential counts. Their shares among buildings with assigned
residential typology are

$$
s_{\mathrm{SFH}}=
100\frac{N_{\mathrm{SFH}}}
{N_{\mathrm{SFH}}+N_{\mathrm{MFH}}},
$$

$$
s_{\mathrm{MFH}}=
100\frac{N_{\mathrm{MFH}}}
{N_{\mathrm{SFH}}+N_{\mathrm{MFH}}}.
$$

If $N_{\mathrm{res}}$ is the number of footprints identified as residential by
`building:flats`, `building:use` or `building`, including typologically
ambiguous residential footprints, residential-typology coverage is

$$
c_{\mathrm{typology}}=
100\frac{N_{\mathrm{SFH}}+N_{\mathrm{MFH}}}{N_{\mathrm{res}}}.
$$

Residential typology contributes to the score for every type when
$c_{\mathrm{typology}}\geq20\,\%$. The target MFH percentage is read directly
from `MFH Anteil (%)` in the unchanged parameter workbook. The compatible
interval extends 15 percentage points either side of that target, clipped to
0–100%. Thus a 0% target accepts 0–15% MFH without penalty; a 100% target
accepts 85–100%. Values outside the interval receive an ordinary normalized
score penalty, without excluding the type. This tolerance is a modelling choice.
Only MFH share is scored because SFH share is its complement; scoring both would
count the same information twice. The tie-break distance uses the workbook
target itself. Below 20% coverage this indicator is omitted from both scores.
Explicit and inferred counts remain exported separately.


An additional eligibility rule is used specifically to distinguish scattered
settlement A from rural village development B. Buildings are grouped and ordered
on the same road side using the procedure above. A continuous frontage run
contains at least three consecutive buildings, with every successive
longitudinal gap no greater than 55 m. Let $I_i^{\mathrm{front}}=1$ when building
$i$ belongs to such a run and zero otherwise. The continuous-road-frontage share
is

$$
s_{\mathrm{front}}=
\frac{100}{N_b}\sum_{i=1}^{N_b}I_i^{\mathrm{front}}.
$$

Type A requires no more than 50% of buildings in continuous frontage runs and
less than 60% participation in the qualifying parallel rows defined below.
Type B requires at least 50% continuous frontage. These structural conditions
and the rural context restriction determine eligibility.
Spacing and attachment contribute only to the ordinary score for A and B.
Their compatible spacing intervals come from the workbook; compatible
attachment is 0–35% for A and 0–50% for B. Outside these intervals the normalized
penalty increases with the deviation, without excluding the type. For example,
36% attachment gives A a small penalty rather than making A ineligible.
There is no minimum number of same-side spacing pairs required for B.


To represent repeated building-row structures, an additional indicator is
calculated from the building centroids. It is deliberately not restricted to
rows perpendicular to roads: both street-following rows and rows inside road
blocks are counted.
Possible row directions are tested at

$$
\theta\in\{0^\circ,5^\circ,10^\circ,\ldots,175^\circ\}.
$$

For each direction, centroid $\mathbf c_i=(x_i,y_i)$ is transformed into an
along-row coordinate $u_i$ and an across-row coordinate $v_i$:

$$
u_i=x_i\cos\theta+y_i\sin\theta,
\qquad
v_i=-x_i\sin\theta+y_i\cos\theta.
$$

Buildings are grouped into the same possible row only while the complete spread
of their across-row coordinates remains no greater than 5 m. This prevents a
row band from gradually widening through chained point additions. Buildings
within that group are ordered by $u_i$. A sequence is interrupted when the
longitudinal gap between two consecutive buildings exceeds 55 m. A possible
row must contain at least four buildings.

A row qualifies only when at least one other parallel row overlaps along at
least 50% of the shorter row's length. The length is measured between the
first and last building centres in the tested direction. For intervals
$[a_r,b_r]$ and $[a_q,b_q]$, the shared length is

$$
L_{rq}=\max\left(0,\min(b_r,b_q)-\max(a_r,a_q)\right).
$$

Both rows qualify when their lengths are positive and

$$
L_{rq}\geq0.50\min(b_r-a_r,b_q-a_q).
$$

Only buildings in rows satisfying this overlap condition contribute to the
participation percentage. Separated stretches without longitudinal overlap
do not qualify together.

For a tested direction $\theta$, let $R(\theta)$ be the set of buildings that
belong to the qualifying rows. A direction qualifies only when it contains at
least two rows. The general row-structure indicator is

$$
s_{\mathrm{rows}}=
100\max_{\theta}\frac{|R(\theta)|}{N_b}.
$$

If no direction produces at least two qualifying rows,
$s_{\mathrm{rows}}=0\,\%$. Types E and F use the interval
$60\,\%\leq s_{\mathrm{rows}}\leq100\,\%$. All other types use
$0\,\%\leq s_{\mathrm{rows}}\leq60\,\%$ in their scores. In addition,
type A is excluded whenever $s_{\mathrm{rows}}\geq60\,\%$; eligibility for A
requires $s_{\mathrm{rows}}<60\,\%$. No row-based hard exclusion is applied
to B–I. Below 60%, E and F receive a row penalty but remain eligible subject
to their other requirements. At exactly 60%, the scored intervals overlap,
but A is excluded. The indicator enters the normalized range and midpoint
scores; FAR remains a
separate indicator and is still omitted when unavailable.

For descriptive review only, the centroid of each detected row is also
associated with its nearest noded road, provided that the road is no farther
than 150 m. The local road direction $\theta_{\mathrm{road},r}$ is measured at
the projected row-centroid position. For row direction $\theta$ and row $r$,
their axial angular difference is

$$
\Delta\theta_r=
\min\!\left(
|\theta-\theta_{\mathrm{road},r}|,
180^\circ-|\theta-\theta_{\mathrm{road},r}|
\right).
$$

The selected direction, number of rows, participating-building count and
median row-to-road angle are exported. The road angle describes whether the
detected rows follow or cross nearby roads, but it does not affect the type
score.


The final active structural condition represents block and frontage structure. Ordinary roads
are noded at intersections and polygonized to identify geometrically closed road
blocks. Service and pedestrian roads are excluded. Roads are examined within an
adaptive context extending one equivalent candidate side length,
$\sqrt{A_{\mathrm{district}}}$, beyond the candidate envelope so that the
envelope does not unnecessarily cut a surrounding block.

For closed block $b$, the denominator is its complete road-boundary perimeter
$P_b$. A selected building inside the block contributes when its footprint is
no farther than 20 m from the block boundary. The complete footprint is projected
onto the closed boundary. At a corner, the projection is allowed to continue
across the end of one road segment and onto the next. Overlapping projected
intervals are merged, so the same part of the boundary is not counted twice.
The resulting unique projected footprint-frontage length is
$L_{\mathrm{covered},b}$, giving

$$
F_b=
\frac{L_{\mathrm{covered},b}}{P_b}.
$$

The merged intervals also divide the remaining uncovered perimeter into
continuous gaps. Let $G_{\max,b}$ denote the longest such gap. Its relative
length is

$$
g_{\max,b}=\frac{G_{\max,b}}{P_b}.
$$

A block satisfies the structural rule only when at least 50% of the complete
perimeter is covered and no single continuous uncovered gap exceeds 35% of the
perimeter. Its qualified frontage value is

$$
F_b^{*}=
\begin{cases}
F_b, & \text{if }F_b\geq0.50\text{ and }g_{\max,b}\leq0.35,\\
0, & \text{otherwise}.
\end{cases}
$$

The candidate indicator is the largest qualified value among its evaluated
closed blocks. Types H and I require $F_{\mathrm{block}}\geq50\,\%$. When no
closed block can be constructed from the available roads, the value remains
missing rather than being interpreted as zero.





## 6. Preliminary settlement-type matching

The source workbook contains nine types:

| Source type | Settlement structure |
|---|---|
| A | Scattered settlement |
| B | Rural village development |
| C | Low-density residential development |
| D | Medium-density residential development |
| E | Row housing development |
| F | Row development with medium density |
| G | High-density row development and high-rise buildings |
| H | Block development |
| I | City centre |

For indicator $x_j$, type $t$ has interval
$[x_{t,j}^{\min},x_{t,j}^{\max}]$. A type-independent normalization scale is
calculated for each indicator from the median width of its nine source-type
intervals:

$$
s_j=\operatorname{median}_{t}
\left(x_{t,j}^{\max}-x_{t,j}^{\min}\right).
$$

The same value $s_j$ is used for all settlement types. The normalized interval
penalty is

$$
p_{t,j}=
\frac{
\max\!\left(
x_{t,j}^{\min}-x_j,
x_j-x_{t,j}^{\max},
0
\right)}
{s_j}.
$$

Thus, $p_{t,j}=0$ when the observed value lies inside the type range. Equal
physical deviations from two type intervals receive equal penalties; a type
does not receive a smaller out-of-range penalty merely because its interval is
wider. The range score is the mean squared penalty across the $m$ available
matching indicators:

$$
D_t=\frac{1}{m}\sum_{j=1}^{m}p_{t,j}^2.
$$

To distinguish types whose range scores are all zero, the midpoint of each
type interval is

$$
x_{t,j}^{\mathrm{mid}}=
\frac{x_{t,j}^{\min}+x_{t,j}^{\max}}{2}.
$$

The normalized midpoint distance is

$$
c_{t,j}=
\frac{
\left|x_j-x_{t,j}^{\mathrm{mid}}\right|
}{
s_j
},
$$

and the combined midpoint score is

$$
C_t=\frac{1}{m}\sum_{j=1}^{m}c_{t,j}^2.
$$

Missing FAR is omitted. Candidates are scored using BCR, building density,
available FAR, the active building-spacing value, attached-building percentage
and general row structure. The active spacing value is normally the median
same-road-side centroid spacing; the median nearest-building-centroid distance
is used when no valid same-road-side pair exists. Repeated rows support both E
and F through the same normalized scoring procedure. Row direction relative to
nearby roads does not alter the score.

The A/B frontage conditions, the type-A row-structure limit and settlement
context determine eligibility. Spacing and attachment enter $D_t$ and $C_t$
as ordinary scored indicators only. Deviations from their compatible ranges
do not exclude A or B. Type B has no minimum spacing-pair requirement.

Residential typology is an additional scored indicator for all nine types when
the 20% coverage condition from Section 5.1 is satisfied. Its MFH-share interval
is centred on the workbook target with a tolerance of 15 percentage points,
clipped to 0–100%. It enters $D_t$ and its distance to the workbook target enters
$C_t$, using a common normalization scale across types. No residential-typology
hard exclusion is applied. Below the coverage threshold the term is omitted.

Block frontage is treated as an eligibility requirement rather than another
term in the averaged score. Types H and I are eligible only when a reconstructed
closed road block satisfies both frontage conditions defined in Section 5.1:
$F_{\mathrm{block}}\geq50\,\%$ and $g_{\max}\leq35\,\%$. If no closed block can
be reconstructed, or if either condition is not satisfied, H and I are excluded
for that candidate. Satisfying the requirement does not add a zero-valued term
to $D_t$ or $C_t$. Consequently, all eligible types are compared using the same
set of scored indicators.

Settlement context is applied as a direct eligibility restriction rather than
as an additional score or penalty. For candidate geometry $\Omega_d$, the
surrounding context zone is the 500 m ring

$$
\Omega_{\mathrm{context}}=
\left(
\operatorname{buffer}(\Omega_d,500\ \mathrm{m})
\cap\Omega_{\mathrm{analysis}}
\right)\setminus\Omega_d.
$$

The candidate itself is therefore excluded. Within this ring, the method
calculates eligible-building density $\rho_{\mathrm{context}}$ and building
coverage ratio $\mathrm{BCR}_{\mathrm{context}}$. Only two context classes are
used. The context is urban when

$$
\mathrm{URBAN}
\quad\text{if}\quad
\rho_{\mathrm{context}}\geq20\ \mathrm{ha}^{-1}
\;\text{or}\;
\mathrm{BCR}_{\mathrm{context}}\geq0.20
\;\text{or}\;
\left(
\rho_{\mathrm{context}}\geq15\ \mathrm{ha}^{-1}
\;\text{and}\;
\mathrm{BCR}_{\mathrm{context}}\geq0.15
\right).
$$

Every other context is classified as rural. In this classification, `RURAL`
therefore means rural or non-urban surroundings; it is deliberately broader
than the strict condition used to activate the rural influence boundary in
Section 4.6. The permitted source types are:

| Settlement context | Eligible types |
|---|---|
| Rural/non-urban | A, B, C, D, E, F, G |
| Urban | C, D, E, F, G, H, I |

Types outside the corresponding set are excluded before the existing range and
midpoint rules are applied. No context penalty is added. For transparency, the
output also stores the type that would have been assigned without the context
restriction and whether the restriction changed the final type.

The assignment rules are:

- exactly one type with $D_t=0$: assign that type with reason
  `unique_compatible`;
- multiple types with $D_t=0$: assign the compatible type with the smallest
  midpoint score $C_t$, with reason `midpoint_tiebreak`; this ordinary midpoint
  comparison also applies when both B and C are compatible;
- no type with $D_t=0$: assign the type with the smallest range score $D_t$,
  with reason `nearest_outside_ranges`.

If the relevant total scores are exactly equal, the alphabetically first type
code is selected to keep the result deterministic.

The selected proposal is then converted into one of three classification-quality
categories:

- `exact` when $D_t=0$;
- `approximate` when $0<D_t\leq1$;
- `unclassified` when $D_t>1$.

Exact and approximate candidates receive the proposed source type. A candidate
with $D_t>1$ receives the final label `UNCLASSIFIED`. Its best proposed source
type and all scores remain available for review, but it is excluded from
type-specific building-use and non-residential-use aggregates. Candidate
membership is retained, so an unclassified candidate remains visible and its
buildings are not reused by another candidate.

The compatible types, nearest range type, proposed and final assignment reasons,
classification-quality category, total range and midpoint scores, unrestricted
type, context class, context-allowed types, context-change flag and individual
indicator diagnostics are retained in the candidate table.








## 7. Building-use classification

### 7.1 Main-use categories

The building population used for use analysis is exactly the population used to
calculate candidate building counts. Each building is assigned one main-use
category:

- **residential:** its building tag is residential and no classified
  non-residential activity is present;
- **mixed-use:** its building tag is residential and it contains a classified
  non-residential activity;
- **non-residential:** its building tag is explicitly non-residential or a
  classified non-residential activity is present;
- **unknown:** neither the building tag nor a contained activity provides enough
  information.

Residential use evidence includes `building:flats>=1` and the tags
`residential`, `apartments`, `bungalow`, `farm`, `house`, `detached`,
`semidetached_house`, `terrace` and `dormitory`. When present,
`building:flats` is evaluated before `building:use`, and `building:use` is
evaluated before the main `building` tag. Explicit non-residential tags include
commercial, retail, office, industrial, warehouse, education, healthcare,
public, cultural, sports and food-service buildings.

Generic `building=yes` alone does not establish a use and is therefore classified
as unknown unless an informative POI is assigned to it.

### 7.2 Assignment of POIs to buildings

OSM features with a recognizable non-residential activity are converted to
representative points. A POI is assigned to a building when its representative
point lies within that building footprint. POIs without a containing eligible
building are recorded diagnostically but excluded from building-based ratios.

When several direct tags or POIs could assign different subtypes to one
building, the first category in this priority order is retained:

**HOSPITAL → UNI → SC → GS → RE → SPORT → CULTURE → WORKSHOP → RETAIL → OB → OTHER_NRB**

This priority resolves competing categories from different POIs or from a POI
and a directly tagged footprint. On an individual object, an explicit
`healthcare` value is resolved first: pharmacy is retail, listed medical uses
are HOSPITAL, and other healthcare services are OTHER_NRB. `amenity=pharmacy`
also identifies retail. For building-type rules, a non-empty `building:use`
replaces the main `building` value, so current use can override the building's
original purpose. Negative office, shop and healthcare tags provide no activity
evidence.

The categories are:

| Code | Non-residential building type |
|---|---|
| OB | Office building |
| SC | School, kindergarten or childcare building |
| RE | Restaurant, café or other food-service building |
| GS | Grocery store |
| UNI | University or college building |
| HOSPITAL | Hospital, clinic or other identified medical facility |
| CULTURE | Cultural facility |
| SPORT | Sports facility |
| RETAIL | Other retail building |
| WORKSHOP | Workshop, manufacturing, warehouse or industrial building |
| OTHER_NRB | Identified non-residential use outside the ten model categories |

The following tag rules determine the subtypes:

| Category | Tag evidence and additions |
|---|---|
| OB | Active `office=*`, office/government building type or use, and `amenity=townhall` or `courthouse`. Generic commercial buildings do not establish office use. |
| SC | School, kindergarten, childcare and `amenity=music_school`. College is assigned UNI under the category priority. |
| UNI | University or college amenity/building type. |
| GS | Supermarket, convenience, grocery, greengrocer, bakery, butcher, deli, beverages, alcohol, seafood, frozen_food and health_food shops; supermarket buildings. |
| RE | Restaurant, cafe, fast_food, bar, pub, biergarten, food_court and ice_cream amenities; restaurant/cafe/pub buildings. |
| RETAIL | Remaining active shops and retail/kiosk buildings; `amenity=pharmacy` or `healthcare=pharmacy`. |
| CULTURE | Existing theatre, cinema, arts centre, community centre, library, events venue, museum, gallery and artwork evidence; conference_centre, exhibition_centre, music_venue and planetarium amenity/tourism tags. |
| SPORT | Sports leisure tags, sport tags and sports buildings, including sports_centre and riding_hall. |
| WORKSHOP | Craft and industrial activity, industrial/warehouse/workshop/manufacture/factory buildings and `man_made=works`. Industrial-site exclusions still apply before candidate analysis. |
| HOSPITAL | Hospital/clinic buildings; hospital, clinic, doctors or dentist amenities; healthcare values hospital, clinic, doctor, dentist, dialysis, medical_imaging or rehabilitation. This is a grouped medical category, not exclusively large hospitals. |
| OTHER_NRB | Other healthcare practices; hotels/hostels/motels/guest houses; worship buildings, police/fire stations, social facilities/nursing homes, post offices, station/transport buildings, barns/stables and other agricultural outbuildings. Also language_school and training amenities pending local validation, and generic non-residential buildings without a more specific subtype. |

`building=farm` describes a residential farmhouse and remains residential;
`barn`, `stable`, `cowshed`, `sty` and `farm_auxiliary` describe agricultural
outbuildings. Dormitories remain MFH-like under the residential typology rule.
OTHER_NRB is an analysis category only; the generator retains its ten NRB types.
It participates in the main-use split and subtype exports. A residential
building with a contained OTHER_NRB activity is mixed-use; an otherwise generic
footprint with that activity is non-residential.




## 8. Aggregation and denominators

Let $N_{\mathrm{res}}$, $N_{\mathrm{mix}}$, $N_{\mathrm{nonres}}$ and
$N_{\mathrm{unknown}}$ denote the numbers of buildings in the four main-use
categories. The total and known-use populations are

$$
N_{\mathrm{all}}=
N_{\mathrm{res}}+N_{\mathrm{mix}}+N_{\mathrm{nonres}}+N_{\mathrm{unknown}},
$$

$$
N_{\mathrm{known}}=
N_{\mathrm{res}}+N_{\mathrm{mix}}+N_{\mathrm{nonres}}.
$$

For category $u\in\{\mathrm{res},\mathrm{mix},\mathrm{nonres}\}$, the share
of all buildings is

$$
p_u^{\mathrm{all}}=
\frac{N_u}{N_{\mathrm{all}}},
$$

whereas the conditional known-use share is

$$
p_u^{\mathrm{known}}=
\frac{N_u}{N_{\mathrm{known}}}.
$$

The unknown-use share is

$$
p_{\mathrm{unknown}}=
\frac{N_{\mathrm{unknown}}}{N_{\mathrm{all}}}.
$$

Let $N_k^{\mathrm{NRB}}$ be the number of buildings assigned NRB subtype
$k$, and let

$$
N_{\mathrm{NRB}}=
\sum_k N_k^{\mathrm{NRB}}.
$$

The conditional NRB subtype share is

$$
p_k^{\mathrm{NRB}}=
\frac{N_k^{\mathrm{NRB}}}{N_{\mathrm{NRB}}}.
$$

The NRB denominator includes identified non-residential activities in mixed-use
buildings. It is therefore not identical to $N_{\mathrm{nonres}}$, which counts
only buildings whose main-use category is non-residential.

The subtype denominator includes OTHER_NRB. The ten generator subtype shares
therefore sum to less than 100% whenever OTHER_NRB is present; all eleven analysis
shares sum to 100% when the denominator is nonzero.

Because natural candidate sizes can differ, the outputs retain two aggregation
perspectives. The pooled, building-weighted share for type $t$ is calculated
from the sums of category counts across all districts of that type. Larger
districts therefore contribute more observations. The district-weighted result
first calculates the percentage within every district and then reports the
unweighted mean across districts of type $t$. Every district therefore
contributes equally. The pooled results are written to the dedicated building-
split and NRB summary files; the means of district-level percentages are
included in `osm_use_summary_by_type.csv`.



## 9. Quality-control conditions and exported outputs

The run checks that:

- every accepted candidate contains 10–70 buildings;
- the use-analysis population equals the morphology population for every
  candidate;
- a building occurs in at most one accepted candidate;
- accepted candidate polygons do not overlap;
- all exported candidate geometries are valid after GeoJSON serialization; and
- the assigned-building layer in the review map reproduces the exported
  building membership count for every candidate; and
- the parameter workbook hash is unchanged.

Each output candidate retains its identifier, membership method, building count,
area, matching indicators, compatible types, nearest
type, proposed type, final assigned type, assignment reason, classification
quality, inclusion in type-specific results, total range and midpoint scores,
indicator-specific penalties and midpoint distances, and unknown-use percentage.
The map popup displays the final type, classification quality, assignment
reason, context, compatible and eligible types, and total type scores. The
residential-typology coverage, known SFH/MFH shares, conditional-typology flag,
continuous frontage, row metrics, adaptive hull ratio, boundary method and
unknown-use percentage remain available in `candidate_metrics.csv` but are
omitted from the popup. It displays the final rural/urban context
label but omits context area, context building count, context density and
context BCR to keep the popup concise. The rural-influence-boundary flag and
locally calculated rural-boundary reach are likewise omitted from the popup.
Initial context density and initial context BCR are also omitted. These
diagnostic values, together with the unrestricted assigned type and the flag
showing whether context changed the assignment, remain available in
`candidate_metrics.csv` for traceability. The popup also omits the separate
context-allowed-type list and block-frontage pass/fail field because both are
already reflected in `Eligible types`. Their underlying values remain in the
candidate table for detailed checks. Indicator-specific range penalties and
midpoint distances are also omitted from the popup to keep it readable; they
remain fully available in `candidate_metrics.csv`. The complete all-type
requirement-check string is likewise omitted from the popup. The all-type range
and midpoint scores remain visible, with one settlement type shown per line so
the values fit the popup more clearly. Building spacing, its calculation source
and the number of same-road-side spacing pairs are also omitted from the popup;
they remain in `candidate_metrics.csv` and continue to be used by the
classification method. The counts of SFH-like, MFH-like, known, unknown and
total residential-typology buildings are also omitted from the popup. They
remain in the candidate table for analysis. Building membership
is exported separately using OSM object identifiers. The review map draws the
exact OSM footprints used in the analysis using the same classification-quality
colors as their candidate. Eligible but
unassigned footprints lying within 30 m of any candidate are available as an
optional grey context layer. Roads retained for clustering are available as a
separate optional layer. The excluded `landuse=industrial` polygons are shown
by default in black. The layer can be hidden or restored through either the map
legend or the layer control. Clicking a building reports its OSM identifier,
footprint area and district membership. The Esri background is used only for
geographic context and is not used to verify building presence or membership.

The combined legend and filter distinguishes three classification qualities:

- green: exact match with $D_t=0$;
- blue: approximate match with $0<D_t\leq1$;
- red: unclassified candidate with $D_t>1$; and
- black: excluded OSM industrial land-use area.

The settlement-type buttons A--I and `UNCLASSIFIED` filter both candidate
polygons and their assigned-building footprints. The three quality buttons can
be switched independently, and the industrial-area button independently shows
or hides the black exclusion layer. When all types or quality categories are
initially active, selecting one button isolates it; further buttons can then be
added or removed. `All` restores all candidate types and quality categories,
while `None` hides all candidates and assigned footprints. Nearby-unassigned,
road and background layers remain independent context layers.

The 30 m distance controls only which unassigned context buildings are included
in the review map. It has no influence on candidate construction, indicators or
classification.


## 10. Candidate-generation results

The run identified 4,552 non-overlapping candidates.

| Membership-selection procedure | Candidates |
|---|---:|
| Road-block cluster, including morphology splits | 2,017 |
| Two-sided street cluster, including morphology splits | 2,535 |
| **Total** | **4,552** |

These candidates contain 130,318 unique building footprints, corresponding to
57.594% of the 226,270 eligible footprints remaining after industrial-site
exclusion. The street graph contains 70,108 building-defined sections, of
which 64,224 contain at least one associated building. Rural building-influence
boundaries are applied to 1,691 candidates, or 37.149% of all candidates.

| Indicator | 25th percentile | Median | 75th percentile |
|---|---:|---:|---:|
| Buildings per candidate | 16 | 25 | 40 |
| District area (ha) | 0.512 | 1.173 | 2.745 |
| BCR | 0.112 | 0.252 | 0.338 |
| Building density (buildings/ha) | 10.539 | 26.308 | 44.102 |
| FAR, where available | 0.470 | 0.843 | 1.618 |
| Active building spacing (m) | 4.316 | 6.374 | 8.780 |
| Attached buildings (%) | 62.892 | 80.000 | 92.308 |
| General row structure (%) | 0.000 | 35.355 | 61.765 |
| Total range score $D_t$ | 0.044 | 0.214 | 2.984 |
| Total midpoint score $C_t$ | 0.503 | 1.132 | 6.557 |

Only 135 candidates meet the 66% storey-data coverage requirement for FAR
estimation. Same-road-side spacing is available for 3,430 candidates; the
nearest-neighbour fallback is used for 1,122. The block-frontage requirement is
met by 971 candidates. The row indicator reaches at least 40%
for 2,128 candidates, corresponding to 46.749% of all candidates.

Candidate areas in this run range from 0.058 to 338.889 ha.




## 11. Settlement-type assignment results

| Assigned type | Candidates | Buildings | Unique compatible | Midpoint tie-break | Nearest outside ranges | Morphology-row rule | Unknown use (%) |
|---|---:|---:|---:|---:|---:|---:|---:|
| A | 14 | 175 | 0 | 0 | 14 | 0 | 66.3 |
| B | 183 | 4,003 | 5 | 0 | 178 | 0 | 75.2 |
| C | 879 | 25,334 | 48 | 0 | 831 | 0 | 82.8 |
| D | 236 | 6,305 | 12 | 0 | 224 | 0 | 65.3 |
| E | 2,869 | 82,272 | 103 | 0 | 2,766 | 0 | 82.6 |
| F | 116 | 3,145 | 0 | 0 | 8 | 108 | 82.7 |
| G | 29 | 537 | 3 | 2 | 24 | 0 | 45.6 |
| H | 23 | 608 | 0 | 0 | 23 | 0 | 38.8 |
| I | 203 | 7,939 | 33 | 0 | 170 | 0 | 60.5 |
| **Total** | **4,552** | **130,318** | **204** | **2** | **4,238** | **108** | **79.8** |

Of the 4,552
assignments, 204 were unique compatible matches, two used the midpoint tie-break,
4,238 selected the nearest eligible type outside all prescribed ranges, and 108
used the explicit morphology-row rule for F. The current method retains such a
proposal only when $D_t\leq1$ and labels poorer proposals `UNCLASSIFIED`.

The final context classes contain 3,650 rural/non-urban and 902 urban
candidates. The direct context restriction changes 208 assignments, or 4.569%,
relative to unrestricted scoring. The assigned set contains 14 A candidates
and 183 B candidates; these counts do not validate the resulting labels.



## 12. Overall main building-use results

| Main-use category | Buildings | Percentage of all buildings | Percentage of known-use buildings |
|---|---:|---:|---:|
| Residential | 22,386 | 17.178% | 85.222% |
| Mixed-use | 934 | 0.717% | 3.556% |
| Non-residential | 2,948 | 2.262% | 11.223% |
| Unknown | 104,050 | 79.843% | — |
| **Total** | **130,318** | **100.000%** | — |

Only 26,268 buildings, or 20.157% of the candidate building population, have a
known main use. The unknown-use share must therefore accompany every use-share
interpretation.

## 13. Main-use results by assigned type

Percentages in the first four result columns use all buildings. The final three
columns are conditional on known-use buildings. The known-use count shows the
denominator supporting those conditional percentages.

| Type | Residential, all | Mixed, all | Non-residential, all | Unknown | Known-use buildings | Residential, known | Mixed, known | Non-residential, known |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A | 17.7% | 0.0% | 16.0% | 66.3% | 59 | 52.5% | 0.0% | 47.5% |
| B | 20.3% | 0.2% | 4.3% | 75.2% | 993 | 81.8% | 0.9% | 17.3% |
| C | 15.6% | 0.1% | 1.6% | 82.8% | 4,365 | 90.4% | 0.6% | 9.0% |
| D | 25.9% | 0.5% | 8.3% | 65.3% | 2,188 | 74.6% | 1.3% | 24.0% |
| E | 15.4% | 0.5% | 1.5% | 82.6% | 14,317 | 88.3% | 3.1% | 8.6% |
| F | 16.1% | 0.1% | 1.0% | 82.7% | 543 | 93.4% | 0.7% | 5.9% |
| G | 27.9% | 2.4% | 24.0% | 45.6% | 292 | 51.4% | 4.5% | 44.2% |
| H | 41.3% | 3.8% | 16.1% | 38.8% | 372 | 67.5% | 6.2% | 26.3% |
| I | 30.4% | 4.8% | 4.3% | 60.5% | 3,139 | 76.9% | 12.2% | 10.9% |

The known-use building count states the denominator supporting each row.

## 14. Overall non-residential subtype results

A total of 3,600 buildings receive a specific non-residential subtype. Of these,
1,604 are classified from direct building-level non-residential tags and 1,996
from POIs assigned to a containing building. A further 493 classified POIs do not
have a containing eligible building and are excluded from building ratios.

| NRB subtype | Buildings | Percentage of classified NRB buildings | Percentage of all buildings |
|---|---:|---:|---:|
| Office building (OB) | 329 | 9.139% | 0.252% |
| School (SC) | 339 | 9.417% | 0.260% |
| Restaurant (RE) | 551 | 15.306% | 0.423% |
| Grocery store (GS) | 224 | 6.222% | 0.172% |
| University (UNI) | 140 | 3.889% | 0.107% |
| Hospital/medical (HOSPITAL) | 296 | 8.222% | 0.227% |
| Cultural facility (CULTURE) | 77 | 2.139% | 0.059% |
| Sports facility (SPORT) | 105 | 2.917% | 0.081% |
| Other retail (RETAIL) | 1,077 | 29.917% | 0.826% |
| Workshop/industrial (WORKSHOP) | 462 | 12.833% | 0.355% |
| **Total** | **3,600** | **100.000%** | **2.762%** |

## 15. Non-residential subtype results by assigned type

The percentages below are conditional on subtype-classified NRB buildings
within each assigned type. Small denominators, particularly for A, B, F and G,
do not support stable type-specific inference.

| Type | NRB buildings | OB | SC | RE | GS | UNI | Hospital | Culture | Sport | Retail | Workshop |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A | 27 | 14.8% | 3.7% | 7.4% | 0.0% | 37.0% | 0.0% | 0.0% | 18.5% | 7.4% | 11.1% |
| B | 149 | 10.1% | 6.7% | 11.4% | 0.7% | 18.1% | 3.4% | 0.7% | 5.4% | 14.1% | 29.5% |
| C | 337 | 7.1% | 18.7% | 14.2% | 4.2% | 3.0% | 6.2% | 5.0% | 4.2% | 19.0% | 18.4% |
| D | 487 | 11.7% | 15.2% | 4.5% | 7.0% | 0.4% | 5.5% | 1.6% | 3.9% | 24.2% | 25.9% |
| E | 1,612 | 6.9% | 8.4% | 19.1% | 7.3% | 0.7% | 8.8% | 1.9% | 2.4% | 34.7% | 9.7% |
| F | 32 | 12.5% | 6.2% | 9.4% | 3.1% | 0.0% | 6.2% | 3.1% | 3.1% | 31.2% | 25.0% |
| G | 126 | 9.5% | 10.3% | 6.3% | 3.2% | 39.7% | 1.6% | 1.6% | 5.6% | 11.1% | 11.1% |
| H | 110 | 16.4% | 10.0% | 3.6% | 4.5% | 16.4% | 11.8% | 2.7% | 1.8% | 24.5% | 8.2% |
| I | 720 | 11.5% | 4.2% | 19.3% | 6.5% | 1.7% | 11.7% | 1.9% | 1.4% | 36.4% | 5.4% |

Small subtype denominators require correspondingly cautious interpretation.

## 16. Result files

The documented outputs are stored in the run directory recorded above:

- `candidate_districts.geojson`: candidate geometries and indicators;
- `candidate_metrics.csv`: district-level morphology and matching results;
- `building_membership.csv`: traceable OSM building membership;
- `osm_use_counts_by_district.csv`: district-level counts and shares;
- `osm_building_split_percentages_by_type.csv`: pooled main-use shares;
- `osm_nrb_building_percentages_by_type.csv`: pooled NRB subtype shares;
- `osm_use_summary_by_type.csv`: extended type summary;
- `review_map.html`: interactive candidate map with exact assigned footprints,
  nearby unassigned footprints and clustering-road layers;
- `manifest.json`: hashes, parameters, package versions and provenance.

`industrial_exclusion_sites.geojson` contains the excluded industrial areas.
The manifest and report record their total area and excluded building count,
the binary context thresholds, and the number of rural influence boundaries.

The review map is approximately 127.6 MB because it embeds the exact assigned
building geometries. Its background map provides context only; visual
membership review must use the blue assigned-footprint layer and the optional
grey nearby-unassigned layer.

OSM data attribution: © OpenStreetMap contributors, ODbL.
