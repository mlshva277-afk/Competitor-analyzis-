"""Streamlit Community Cloud entry point: open the demo on the first visit."""
import os
from pathlib import Path
import runpy

os.environ['ISI_DEFAULT_DEMO'] = '1'
runpy.run_path(str(Path(__file__).with_name('app.py')), run_name='__main__')
