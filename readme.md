
### Code structure

```
rf_measurements/
├── __init__.py
├── cli.py                # common CLI parsing, prompt, temperature validation
├── common/
│   ├── __init__.py
│   ├── logging.py        # shared logging configuration
│   ├── net.py            # _discover_net_folders, NetFolder dataclass
│   ├── io.py             # helpers for creating plots/, writing reports
│   └── errors.py         # custom exception definitions
├── gain/
│   ├── __init__.py
│   ├── converter.py      # code that used to be in gain_compression_to_mdif.py
│   └── cli.py            # thin wrapper that calls common CLI then converter
├── imd/
│   ├── __init__.py
│   ├── converter.py
│   └── cli.py
├── nf/
│   ├── __init__.py
│   ├── converter.py
│   └── cli.py
├── s2p/
│   ├── __init__.py
│   ├── converter.py
│   └── cli.py
└── scripts/
    ├── master_mdif_generator_nl_char.py
    └── master_mdif_generator_linear_char.py
```