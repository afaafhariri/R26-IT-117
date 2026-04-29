class FinishingBOQ:
    def calculate(self, building_schema: dict, finish_grade: str) -> dict:
        footprint_sqm = building_schema.get('footprint_sqm', 0.0)
        return {
            "floor_tile_sqm": footprint_sqm * 0.9,
            "wall_plaster_sqm": footprint_sqm * 2.5
        }
