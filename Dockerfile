FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY routers ./routers
COPY forecast_engine ./forecast_engine
COPY services ./services
COPY institutional_conviction_engine.py .
COPY execution_intelligence_engine.py .
COPY decision_engine.py .
COPY forecast_client.py .
COPY technical_engine.py .
COPY breadth_engine.py .
COPY cross_asset_engine.py .
COPY news_impact_engine.py .
COPY treasury_yield_engine.py .
COPY sector_rotation_engine.py .
COPY vix_term_structure_engine.py .
COPY credit_spread_engine.py .
COPY static ./static
COPY options ./options

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8004"]
