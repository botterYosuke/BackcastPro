from math import nan
import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

import pandas as pd
from BackcastPro import *

df = chart('2371', '2025-01-01', '2025-01-31')
print(df)


# next()
# next_day()
# chart()