class DistrictMultiplier:
    def __init__(self):
        self.multipliers = {
            "Colombo": 1.00,
            "Gampaha": 1.02,
            "Kandy": 1.05,
            "Ampara": 1.12,
            "Trincomalee": 1.14,
            "Vavuniya": 1.18,
            "Mullaitivu": 1.22
        }
    def get_multiplier(self, district: str) -> float:
        return self.multipliers.get(district, 1.0)
    def apply(self, base_rate: float, district: str) -> float:
        return base_rate * self.get_multiplier(district)
