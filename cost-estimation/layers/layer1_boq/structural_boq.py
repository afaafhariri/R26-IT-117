class StructuralBOQ:
    def calculate(self, building_schema: dict) -> dict:
        perimeter = building_schema.get('perimeter', 0.0)
        footprint_sqm = building_schema.get('footprint_sqm', 0.0)
        
        return {
            "foundation_excavation_m3": perimeter * 1.5 * 0.6,
            "blinding_concrete_m3": perimeter * 0.6 * 0.05,
            "foundation_concrete_m3": perimeter * 0.6 * 0.45,
            "rc_slab_m3": footprint_sqm * 0.125,
            "roof_area_sqm": footprint_sqm * 1.30
        }
