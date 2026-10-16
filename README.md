# Nassau Candy - Shipping Route Efficiency

## Files
- `app.py` - Streamlit dashboard
- `analysis.py` - data cleaning and route calculations (used by the dashboard)
- `Nassau_Candy_Distributor.csv` - the data (must sit in the same folder as app.py)
- `requirements.txt`, `figures/` - dependencies and the charts used in the paper

## Run the dashboard (step by step)
1. Install Python 3.10 or newer from python.org (tick "Add Python to PATH" on Windows).
2. Open a terminal (Command Prompt on Windows) and go into this folder:
   `cd path\to\nassau_project`
3. Install the libraries: `pip install -r requirements.txt`
4. Start it: `streamlit run app.py`
5. Your browser opens at http://localhost:8501. Press Ctrl+C in the terminal to stop.

## Important note on the data
Raw ship dates are 904-1,642 days after order dates. `analysis.py` subtracts a fixed offset per Order-ID year
(the Same Day minimum) to get realistic lead times. Confirm this with whoever supplied the data.
