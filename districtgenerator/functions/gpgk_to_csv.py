import argparse
from pathlib import Path


def convert_gpkg(gpkg_path, output_path=None, layer=None):
    """Export point coordinates in EPSG:25833 and retain the cadastre attributes."""
    import geopandas as gpd

    gpkg_path = Path(gpkg_path)
    output_path = Path(output_path) if output_path else gpkg_path.with_suffix(".csv")
    if output_path.exists():
        raise FileExistsError(f"Output already exists: {output_path}. Choose another --output path.")
    layers = list(gpd.list_layers(gpkg_path)["name"])
    if layer is None:
        if len(layers) != 1:
            raise ValueError(f"Choose --layer from: {', '.join(layers)}")
        layer = layers[0]
    gdf = gpd.read_file(gpkg_path, layer=layer)
    if gdf.crs is None:
        raise ValueError("The input layer has no coordinate reference system.")
    if not gdf.geometry.geom_type.eq("Point").all() or gdf.geometry.is_empty.any():
        raise ValueError("Select the heat-cadastre point layer; polygon layers are not supported.")
    gdf = gdf.to_crs(epsg=25833)
    gdf["x"] = gdf.geometry.x
    gdf["y"] = gdf.geometry.y
    output_path.parent.mkdir(parents=True, exist_ok=True)
    gdf.drop(columns=[gdf.geometry.name]).to_csv(output_path, index=False)
    return output_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gpkg", type=Path)
    parser.add_argument("--layer", help="Required when the GeoPackage has multiple layers.")
    parser.add_argument("--output", type=Path, help="Default: input filename with .csv extension.")
    args = parser.parse_args()
    print(convert_gpkg(args.gpkg, args.output, args.layer))


if __name__ == "__main__":
    main()
