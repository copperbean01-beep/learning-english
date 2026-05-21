
python3 -m venv .venv && source .venv/bin/activate && python -m pip install streamlit

python3 -m streamlit run app.py

Specify port/host:
python3 -m streamlit run app.py --server.port 8501 --server.address 0.0.0.0

Run detached and capture logs:
nohup python3 -m streamlit run app.py --server.port 8501 > streamlit.log 2>&1 &