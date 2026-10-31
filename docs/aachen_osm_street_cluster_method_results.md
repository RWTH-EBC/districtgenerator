# Automated district discovery and OSM/NRW building-use analysis for StädteRegion Aachen

The method combines settlement morphology, building-use classification and
generation probabilities using OSM geometry and supplementary NRW building evidence.
Explicit sports halls and fitness centres supply
the SPORT archetype. Generation probabilities use residential, mixed-use and
supported non-residential buildings. Unknown uses and unsupported pure
non-residential buildings are excluded from these probabilities for all types.



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
`sport`, `man_made`, `railway` and `public_transport`. The source snapshot
records the retrieval date, query attributes and source-feature counts.

All metric geometric operations are performed in ETRS89 / UTM zone 32N
(EPSG:25832). Map outputs are transformed to WGS 84 (EPSG:4326).

### 2.2 Parameter workbook and random seed

The literature-derived parameter table supplies the minimum and
maximum BCR, building-density and FAR values for source settlement types A–I.
Source snapshots, parameter values and software versions are recorded for
reproducibility. Content hashes identify the input datasets and parameter table.
Random ordering of road seeds uses seed 2026.



### 2.3 Analytical extent

The regional analysis covers the complete administrative area of
StädteRegion Aachen. Source geometries are spatially restricted to this study
extent before candidate construction and indicator calculation.



### 2.4 NRW building evidence and spatial matching

The NRW municipal heat-planning building dataset (KWP-NRW) supplements missing
OSM attributes for the ten municipalities of StaedteRegion Aachen. Downloaded
municipality packages are identified by source and content hash. The source is
[OpenGeodata NRW, municipal heat planning](https://www.opengeodata.nrw.de/produkte/umwelt_klima/energie/kwp/).

Spatial matching uses projected footprints in EPSG:25832. OSM outlines and roads
are retained; NRW outlines establish correspondence only. No NRW-only buildings
are added. A one-to-one match requires at least 70% coverage of each footprint,
intersection-over-union of at least 60%, and no alternative covering 20% or more
of the OSM footprint. For contained parts, each selected NRW part must be at
least 80% contained and their union must cover at least 85% of the OSM footprint.
Rejected or absent correspondences remain unresolved; nearest-neighbour filling
is not used. Overlapping alternative source representations can still require
review even when a contained-parts match is accepted.

Supplementary fields are supplied before eligibility filtering and clustering:

| Attribute | Evidence priority and use |
|---|---|
| Main building use | Explicit OSM use and compatible contained POIs take priority; accepted NRW evidence fills unknown main use. |
| NRB subtype | Specific supported OSM evidence is retained. Specific NRW functions can fill a missing supported subtype; broad functions remain OTHER_NRB. |
| Storeys | Explicit OSM storeys take priority; NRW calculated storeys fill gaps for the FAR calculation and its coverage rule. |
| Residential typology | Explicit OSM evidence precedes modelled NRW EFH/RH or MFH/GMFH labels; footprint-based inference is the final fallback. |
| Construction period | NRW assigned age classes supplement provisional year evidence for later real-district evaluation, not clustering or type scoring. |
| Energy condition | Modelled NRW condition classes support later evaluation; they are not verified renovation histories and do not enter type scoring. |

NRW subtype mapping requires sufficiently specific function evidence. For
example, `31001_2120` (Werkstatt) supports WORKSHOP, whereas generic factory,
warehouse and commercial functions do not independently establish that
archetype. Explicit sports-hall evidence supports SPORT; generic sports functions
do not establish a heated hall. The OSM tag crosswalk in Section 7 includes
industrial/warehouse WORKSHOP mapping. Source
priority therefore does not make the two source crosswalks identical. Ordinary
use and storey disagreements remain flagged rather than overwritten.

The clustering algorithm uses OSM geometry and accepted supplementary NRW
attributes. Literature ranges define settlement types; the run configuration
specifies grouping settings and the random seed. Memberships and boundaries
are calculated from the eligible building population.
Assigned age and condition classes are model-derived inputs, not observations.

Supplementary attributes are assigned only to accepted spatial matches.
Source identifiers and matching decisions are recorded for traceability.

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
The number of excluded footprints is reported with the analysis results.

Generic `building=yes` footprints are retained. Their use may be unknown, but
excluding them would distort building count, density and coverage.

Accepted NRW evidence can identify generic OSM footprints as garages
(`31001_2463`) or sheds (`31001_2723`), to which the same exclusions apply.
Utility-only matches with exclusively `31001_25xx` functions are excluded for
generic or explicitly technical OSM building tags only when no conflicting
ordinary-use evidence exists. Residential tags, flat counts, ordinary
non-residential uses and compatible contained POIs protect a footprint from
automatic utility exclusion. Mixed NRW functions and source disagreements remain
flagged for review. Modelled unheated status is not a general exclusion rule.
Raw OSM tags are preserved as evidence; supplementary eligibility flags do not
rewrite them. These rules apply before grouping to all settlement types.

Exact duplicate geometries are removed. A smaller polygon is also removed when
more than 98% of its area is covered by a polygon whose area is more than 1%
larger. This is intended to remove duplicate OSM way/relation representations.
The eligible footprint count is recorded and included in
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
otherwise eligible buildings are recorded as exclusion diagnostics.

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

Selective service-road inclusion requires the OSM `service` attribute.
If this attribute is unavailable, service roads are excluded because access
roads cannot be distinguished reliably.



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
from `MFH Anteil (%)` in the parameter workbook. The compatible
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

For SPORT, a representative point alone is not sufficient when the POI has
polygon geometry: the complete sports-hall or fitness-centre polygon must be
covered by the containing building footprint. Point POIs must lie inside the
footprint. Parking, garages, grandstands, stadiums, pavilions and riding halls
cannot become SPORT through a contained POI. In addition, contained POIs cannot
promote an otherwise unsupported grandstand, pavilion or riding hall to a
heated cultural or other supported archetype.

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

SPORT additionally checks both physical `building` and `building:use` tags:
an incompatible structure cannot become a sports hall solely through an
overriding use tag.

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
| SPORT | Indoor sports hall or explicitly identified fitness centre |
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
| SPORT | Explicit `building=sports_hall`, `building:use=sports_hall`, `leisure=sports_hall` or `leisure=fitness_centre`, subject to compatible building evidence and the POI-containment conditions above. |
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

### 7.3 SPORT exclusions and thermal-archetype interpretation

The SPORT category supplies the thermal `Turnhalle` archetype. Including an
explicit fitness centre is an agreed modelling approximation: its opening
hours, ventilation, showers and heat demand need not equal those of a sports
hall. The tags establish facility-use evidence, not actual heating or energy
intensity. The following evidence is insufficient for SPORT:

| Evidence | Treatment |
|---|---|
| `sport=fitness` alone or outdoor `leisure=fitness_station` | Activity evidence only; does not establish an indoor fitness centre. |
| Other `sport=*` alone, such as soccer or shooting | Does not establish a sports hall; retain another supported use if independently identified, otherwise no subtype from this tag. |
| Outdoor `leisure=pitch` | Does not establish an indoor building use. |
| Generic `leisure=sports_centre` without explicit hall evidence | OTHER_NRB rather than an automatic Turnhalle proxy. |
| Swimming pool, riding hall, grandstand, stadium or pavilion | Unsupported sports uses, normally OTHER_NRB; not SPORT. Existing independently identified, higher-priority uses remain subject to the classifier's priority rules. |
| Parking or ambiguous sports POI overlapping a footprint | Not SPORT. Without another informative building-use tag, use can remain unknown. |

The source snapshot lacks `indoor`, `covered` and name attributes. Unavailable
tags provide no classification evidence. SPORT eligibility is distinct from
footprint eligibility for geometry and morphology analysis.




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

The raw analysis subtype denominator includes OTHER_NRB. The ten supported
subtype shares in that export therefore sum to less than 100% whenever OTHER_NRB
is present; all eleven analysis shares sum to 100% when the denominator is
nonzero. These raw shares are not the generator's normalized subtype weights.

Because natural candidate sizes can differ, the outputs retain two aggregation
perspectives. The pooled, building-weighted share for type $t$ is calculated
from the sums of category counts across all districts of that type. Larger
districts therefore contribute more observations. The district-weighted result
first calculates the percentage within every district and then reports the
unweighted mean across districts of type $t$. Every district therefore
contributes equally. Both pooled shares and means of district-level
percentages are reported separately.

### 8.1 Generation probabilities and unknown building uses

Raw evidence tables retain all four main-use categories, including unknown.
For generation, all types A--I use the same represented-building denominator.
Unknown-use footprints and pure non-residential buildings without a supported
archetype are excluded from both the relevant numerator and the denominator:

$$
p_{\mathrm{res},t}^{\mathrm{gen}}=
\frac{N_{\mathrm{res},t}}{N_{\mathrm{gen},t}},
\qquad
p_{\mathrm{nonres},t}^{\mathrm{gen}}=
\frac{N_{\mathrm{nonres,supported},t}}{N_{\mathrm{gen},t}},
\qquad
p_{\mathrm{mix},t}^{\mathrm{gen}}=
\frac{N_{\mathrm{mix},t}}{N_{\mathrm{gen},t}}.
$$

Here, N_gen is the sum of residential, mixed-use and supported pure
non-residential counts. Unsupported pure non-residential buildings remain
OTHER_NRB in the raw analysis, but are not redistributed across generation
archetypes. Mixed-use buildings remain included even when their non-residential
activity is unsupported. Unknown buildings are not reclassified as residential
or non-residential. No EFH/MFH, age, retrofit, footprint or floor-area
parameter is inferred from the unknown-use tag. The ten supported NRB
subtype weights retain their separate supported-use denominator.

For all types, generator subtype weights use the supported-category denominator:

$$
w_k^{\mathrm{gen}}=
\frac{N_k^{\mathrm{NRB}}}{\sum_{j\in\mathcal K_{\mathrm{supported}}}N_j^{\mathrm{NRB}}}.
$$

Here $\mathcal K_{\mathrm{supported}}$ contains the ten model categories and
excludes OTHER_NRB. All supported-subtype weights are normalized using this
denominator. SPORT is excluded from
mixed-use draws. Its marginal draw probability is the pure non-residential
main-use share multiplied by its supported-subtype weight.

These probabilities describe stochastic draws, not fixed category counts
within each generated district. Observed building-use shares and generation
probabilities have distinct denominators and are reported separately.



## 9. Quality-control conditions

The run checks that:

- every accepted candidate contains 10–70 buildings;
- the use-analysis population equals the morphology population for every
  candidate;
- a building occurs in at most one accepted candidate;
- accepted candidate polygons do not overlap;
- candidate geometries are valid;
- mapped building memberships agree with the analytical membership counts; and
- the input parameter table is preserved during analysis.

Each output candidate retains its identifier, membership method, building count,
area, matching indicators, compatible types, nearest
type, proposed type, final assigned type, assignment reason, classification
quality, inclusion in type-specific results, total range and midpoint scores,
indicator-specific penalties and midpoint distances, and unknown-use percentage.
Building memberships are traceable through OSM object identifiers. Diagnostic
records distinguish source evidence, missing attributes, model-derived proxies
and source conflicts. Indicator-level penalties and scores for all candidate
types support inspection of the final assignment.

Classification quality is exact for $D_t=0$, approximate for
$0<D_t\leq1$, and unclassified for $D_t>1$. These labels express compatibility
with the morphological criteria, not independent validation of the assigned
type. Background map imagery is geographic context, not building-use evidence.


## 10. Candidate-generation results

The following results describe the `full_staedteregion_aachen` analysis extent.

The run identified 3,627 non-overlapping candidates.

| Membership-selection procedure | Candidates |
|---|---:|
| Road-block clusters, including morphology splits | 2,145 |
| Two-sided street clusters, including morphology splits | 1,461 |
| Additional scattered-A candidates | 21 |
| **Total** | **3,627** |

The candidates contain 95,830 unique building footprints, corresponding to 59.691% of the 160,543 eligible footprints.

| Indicator | 25th percentile | Median | 75th percentile |
|---|---:|---:|---:|
| Buildings per candidate | 15 | 22 | 35 |
| District area (ha) | 0.741 | 1.409 | 2.556 |
| BCR | 0.142 | 0.215 | 0.299 |
| Building density (buildings/ha) | 10.841 | 18.159 | 27.301 |
| FAR, where available | 0.321 | 0.501 | 0.741 |
| Active building spacing (m) | 5.459 | 8.344 | 13.621 |
| Attached buildings (%) | 48.360 | 72.727 | 90.909 |
| General row structure (%) | 0.000 | 40.741 | 63.415 |
| Total range score $D_t$ | 0.034 | 0.127 | 0.352 |
| Total midpoint score $C_t$ | 0.380 | 0.712 | 1.475 |

Sections 12--15 describe building-use evidence, including accepted NRW gap fills when enrichment is enabled. Section 17 gives generation weights after excluding unknown and unsupported pure non-residential buildings. Evidence counts and generation denominators are reported separately.

FAR is available for 2,673 candidates. The block-frontage requirement is met by 1,079 candidates. Rural influence boundaries are applied to 1,766 candidates.

Candidate areas range from 0.093 to 48.005 ha.

## 11. Settlement-type assignment results

| Type | Candidates | Buildings | Exact | Approximate | Unique compatible | Midpoint tie-break | Nearest outside ranges |
|---|---:|---:|---:|---:|---:|---:|---:|
| A | 44 | 641 | 3 | 41 | 3 | 0 | 41 |
| B | 502 | 12,473 | 46 | 456 | 46 | 0 | 456 |
| C | 267 | 6,111 | 17 | 250 | 17 | 0 | 250 |
| D | 448 | 12,726 | 3 | 445 | 3 | 0 | 445 |
| E | 1,663 | 46,899 | 15 | 1,648 | 15 | 0 | 1,648 |
| F | 8 | 162 | 0 | 8 | 0 | 0 | 8 |
| G | 55 | 1,235 | 2 | 53 | 2 | 0 | 53 |
| H | 42 | 1,421 | 0 | 42 | 0 | 0 | 42 |
| I | 90 | 3,551 | 1 | 89 | 1 | 0 | 89 |
| UNCLASSIFIED | 508 | 10,611 | 0 | 0 | 0 | 0 | 0 |

Classification quality is exact for 87, approximate for 3,032 and unclassified for 508 candidates. 3,119 candidates enter type-specific results.

The final context classes contain URBAN=330, RURAL=3,297. Context changes 87 assignments relative to unrestricted scoring.

## 12. Overall main building-use results

| Main-use category | Buildings | Percentage of all | Percentage of known use |
|---|---:|---:|---:|
| Residential | 62,080 | 72.848% | 86.595% |
| Mixed-use | 2,709 | 3.179% | 3.779% |
| Non-residential | 6,901 | 8.098% | 9.626% |
| Unknown | 13,529 | 15.876% | — |
| **Total** | **85,219** | **100.000%** | — |

The known-use population contains 71,690 buildings; 15.876% have unknown main use.

## 13. Main-use results by assigned type

| Type | Buildings | Residential, all | Mixed, all | Non-residential, all | Unknown | Known-use buildings | Residential, known | Mixed, known | Non-residential, known |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A | 641 | 55.9% | 0.9% | 22.6% | 20.6% | 509 | 70.3% | 1.2% | 28.5% |
| B | 12,473 | 69.8% | 1.6% | 7.9% | 20.7% | 9,891 | 88.1% | 2.0% | 9.9% |
| C | 6,111 | 62.5% | 1.8% | 12.4% | 23.3% | 4,686 | 81.5% | 2.3% | 16.2% |
| D | 12,726 | 69.1% | 3.5% | 11.6% | 15.8% | 10,715 | 82.1% | 4.1% | 13.8% |
| E | 46,899 | 78.2% | 2.5% | 5.2% | 14.1% | 40,272 | 91.1% | 2.9% | 6.0% |
| F | 162 | 61.1% | 4.3% | 27.8% | 6.8% | 151 | 65.6% | 4.6% | 29.8% |
| G | 1,235 | 50.9% | 3.3% | 19.6% | 26.2% | 911 | 68.9% | 4.5% | 26.6% |
| H | 1,421 | 60.1% | 10.6% | 19.9% | 9.4% | 1,287 | 66.4% | 11.7% | 22.0% |
| I | 3,551 | 60.0% | 16.9% | 15.2% | 8.0% | 3,268 | 65.2% | 18.4% | 16.5% |

## 14. Overall non-residential subtype results

A total of 9,610 buildings receive a subtype: 1,996 from direct building evidence and 1,380 from contained POIs. 296 classified POIs have no containing eligible building.

| NRB subtype | Buildings | Percentage of classified NRB | Percentage of all buildings |
|---|---:|---:|---:|
| Office (OB) | 391 | 4.069% | 0.459% |
| School (SC) | 413 | 4.298% | 0.485% |
| Restaurant (RE) | 394 | 4.100% | 0.462% |
| Grocery (GS) | 187 | 1.946% | 0.219% |
| University (UNI) | 97 | 1.009% | 0.114% |
| Hospital/medical (HOSPITAL) | 146 | 1.519% | 0.171% |
| Culture (CULTURE) | 73 | 0.760% | 0.086% |
| Sport (SPORT) | 73 | 0.760% | 0.086% |
| Other retail (RETAIL) | 783 | 8.148% | 0.919% |
| Workshop/industrial (WORKSHOP) | 718 | 7.471% | 0.843% |
| Other identified NRB (OTHER_NRB) | 6,335 | 65.921% | 7.434% |
| **Total** | **9,610** | **100.000%** | **11.277%** |

## 15. Non-residential subtype results by assigned type

Percentages are conditional on subtype-classified NRB buildings within each assigned type.

| Type | NRB buildings | OB | SC | RE | GS | UNI | HOSPITAL | CULTURE | SPORT | RETAIL | WORKSHOP | OTHER_NRB |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A | 151 | 4.6% | 3.3% | 5.3% | 1.3% | 0.0% | 0.0% | 3.3% | 0.7% | 3.3% | 10.6% | 67.5% |
| B | 1,179 | 2.9% | 2.7% | 3.2% | 1.7% | 0.3% | 1.0% | 0.7% | 0.4% | 3.6% | 7.5% | 76.1% |
| C | 868 | 3.5% | 6.6% | 2.1% | 1.4% | 0.0% | 0.8% | 1.3% | 1.6% | 5.5% | 8.9% | 68.4% |
| D | 1,919 | 5.7% | 6.9% | 3.6% | 2.2% | 0.7% | 1.5% | 0.6% | 1.3% | 10.2% | 10.0% | 57.4% |
| E | 3,587 | 1.7% | 2.8% | 2.9% | 1.3% | 0.1% | 0.9% | 0.4% | 0.3% | 4.3% | 6.7% | 78.5% |
| F | 52 | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 1.9% | 0.0% | 11.5% | 30.8% | 55.8% |
| G | 283 | 5.3% | 10.2% | 5.3% | 1.8% | 16.3% | 3.5% | 1.1% | 2.5% | 10.2% | 4.6% | 39.2% |
| H | 433 | 13.9% | 5.8% | 5.3% | 2.5% | 5.1% | 5.8% | 0.9% | 1.4% | 17.8% | 6.5% | 35.1% |
| I | 1,138 | 6.4% | 2.7% | 10.4% | 4.3% | 1.0% | 2.7% | 1.3% | 0.3% | 19.9% | 4.1% | 46.9% |

## 16. Result interpretation and traceability

The analysis reports candidate boundaries, building memberships, morphological indicators, type-assignment scores and building-use counts. Type-level summaries distinguish pooled building-weighted shares from district-weighted means. Source identifiers and input provenance support reproducibility; automated type labels require morphological review before treating candidates as validated real districts.

OSM data attribution: © OpenStreetMap contributors, ODbL.

## 17. Generation parameters

Generation weights distinguish observed building uses from modelling assumptions. The subtype weights are conditional on the ten supported NRB categories; OTHER_NRB is not part of this denominator. Unsupported pure non-residential buildings are also excluded from main-use generation shares; residential and mixed-use buildings are included. Raw evidence tables describe all observed uses.

### 17.1 SPORT weights

| Type | SPORT buildings | SPORT among supported NRB |
|---|---:|---:|
| A | 1 | 2.04% |
| B | 5 | 1.77% |
| C | 14 | 5.11% |
| D | 25 | 3.06% |
| E | 12 | 1.55% |
| F | 0 | 0.00% |
| G | 7 | 4.07% |
| H | 6 | 2.14% |
| I | 3 | 0.50% |

### 17.2 Main-use generation weights

| Type | Residential | Non-residential | Mixed | Unknown footprints assigned residential | Marginal SPORT probability |
|---|---:|---:|---:|---:|---:|
| A | 86.68% | 11.86% | 1.45% | 0 | 0.242% |
| B | 94.96% | 2.91% | 2.13% | 0 | 0.052% |
| C | 91.14% | 6.23% | 2.63% | 0 | 0.318% |
| D | 87.98% | 7.62% | 4.40% | 0 | 0.233% |
| E | 95.13% | 1.86% | 3.01% | 0 | 0.029% |
| F | 76.74% | 17.83% | 5.43% | 0 | 0.000% |
| G | 76.40% | 18.61% | 4.99% | 0 | 0.758% |
| H | 71.95% | 15.42% | 12.64% | 0 | 0.329% |
| I | 70.39% | 9.78% | 19.83% | 0 | 0.049% |

All types A--I use the same represented-building denominator: residential plus mixed plus supported pure non-residential buildings. Unknown-use footprints remain unknown; unknowns and unsupported pure non-residential buildings are excluded from generation shares.

### 17.3 Probability interpretation

The main-use weights and supported subtype weights are distinct conditional distributions. Their product determines the marginal probability of a supported non-residential archetype in a stochastic district draw, subject to the mixed-use eligibility rules in Section 8. A weight does not prescribe an exact number of buildings in any individual district.


## 18. NRW enrichment evidence

OSM footprints and roads supply geometry. The NRW municipal building packages supply accepted supplementary attributes before clustering. Specific OSM evidence takes priority; model-derived attributes remain distinguishable from observations.

| Indicator for final candidate members | Count |
|---|---:|
| Member footprints | 95,830 |
| Known main use from OSM | 27,113 |
| Known main use from combined OSM/NRW evidence | 81,076 |
| Remaining unknown main use | 14,754 |
| Explicit OSM storeys | 8,618 |
| Effective storeys including calculated NRW gaps | 72,343 |
| NRW residential-typology labels used | 49,268 |
| Main-use conflict flags | 2,758 |
| Storey conflict flags | 3,802 |

The pre-clustering utility check flags 474 footprints, excludes 423 utility-only footprints, and retains 51 mixed/conflicting flags for review. These counts refer to the initial eligible population, not only final candidate members.

Source identifiers and content hashes identify the building datasets. Age classes and energy-condition proxies are not used for clustering or settlement-type scoring. Model-derived attributes are proxies, not independently verified observations of individual buildings.
