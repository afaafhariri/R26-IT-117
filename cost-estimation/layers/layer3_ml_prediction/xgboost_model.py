class XGBoostCostModel:
    def train(self, X, y): pass
    def predict(self, X) -> float: return 0.0
    def predict_interval(self, X) -> tuple[float, float]: return (0.0, 0.0)
    def save(self, path): pass
    def load(self, path): pass
