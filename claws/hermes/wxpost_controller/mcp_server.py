from .mcp_factory import create_mcp


mcp = create_mcp(
    include_material_mutations=True,
    name="soarhigh-wxpost-controller",
)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
