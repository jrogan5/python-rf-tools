"""Generic MDIF plotter — tkinter window with embedded matplotlib axes."""

import tkinter as tk
from tkinter import ttk
from typing import Dict, List, Tuple

import matplotlib
import numpy as np

matplotlib.use("TkAgg")
import matplotlib.pyplot as plt  # noqa: E402 (must come after backend set)
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure

# (label, {column_name: np.ndarray})
TraceList = List[Tuple[str, Dict[str, np.ndarray]]]

_PANEL_WIDTH = 260  # px, left control panel fixed width


class MDIFPlotterApp:
    def __init__(self, root: tk.Tk, traces: TraceList, title: str = "") -> None:
        self.root = root
        self.root.title(f"rf-plot  —  {title}" if title else "rf-plot")
        self.root.minsize(960, 540)

        self._all_traces = traces

        # Discover columns from the first trace that has data
        first_data = next((d for _, d in traces if d), {})
        self._columns = list(first_data.keys())

        # ── state variables ───────────────────────────────────────
        self._checked: Dict[str, bool] = {lbl: True for lbl, _ in traces}
        self._x_col   = tk.StringVar(value=self._columns[0] if self._columns else "")
        self._y_col   = tk.StringVar(
            value=self._columns[1] if len(self._columns) > 1 else ""
        )
        self._x_min   = tk.StringVar()
        self._x_max   = tk.StringVar()
        self._filter  = tk.StringVar()

        self._build_ui()

        # wire up live-update callbacks after widgets exist
        self._x_col.trace_add("write",  lambda *_: self._refresh_plot())
        self._y_col.trace_add("write",  lambda *_: self._refresh_plot())
        self._x_min.trace_add("write",  lambda *_: self._refresh_plot())
        self._x_max.trace_add("write",  lambda *_: self._refresh_plot())
        self._filter.trace_add("write", lambda *_: self._on_filter_change())

        self._refresh_plot()

    # ── UI construction ───────────────────────────────────────────

    def _build_ui(self) -> None:
        self._build_left_panel()
        self._build_right_panel()

    def _build_left_panel(self) -> None:
        left = ttk.Frame(self.root, padding=8, width=_PANEL_WIDTH)
        left.pack(side=tk.LEFT, fill=tk.Y)
        left.pack_propagate(False)

        # Axis selectors
        ttk.Label(left, text="X-axis column").pack(anchor=tk.W)
        ttk.Combobox(
            left, textvariable=self._x_col, values=self._columns, state="readonly"
        ).pack(fill=tk.X, pady=(0, 6))

        ttk.Label(left, text="Y-axis column").pack(anchor=tk.W)
        ttk.Combobox(
            left, textvariable=self._y_col, values=self._columns, state="readonly"
        ).pack(fill=tk.X, pady=(0, 10))

        # X range
        ttk.Label(left, text="X range").pack(anchor=tk.W)
        rng = ttk.Frame(left)
        rng.pack(fill=tk.X, pady=(0, 10))
        ttk.Entry(rng, textvariable=self._x_min, width=9).pack(side=tk.LEFT)
        ttk.Label(rng, text="  –  ").pack(side=tk.LEFT)
        ttk.Entry(rng, textvariable=self._x_max, width=9).pack(side=tk.LEFT)

        ttk.Separator(left, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=6)

        # Filter
        ttk.Label(left, text="Filter traces").pack(anchor=tk.W)
        ttk.Entry(left, textvariable=self._filter).pack(fill=tk.X, pady=(0, 4))

        # Scrollable checklist
        list_outer = ttk.Frame(left)
        list_outer.pack(fill=tk.BOTH, expand=True)

        vsb = ttk.Scrollbar(list_outer, orient=tk.VERTICAL)
        self._list_canvas = tk.Canvas(
            list_outer, yscrollcommand=vsb.set, highlightthickness=0
        )
        vsb.config(command=self._list_canvas.yview)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._list_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._check_frame = ttk.Frame(self._list_canvas)
        self._list_canvas.create_window((0, 0), window=self._check_frame, anchor="nw")
        self._check_frame.bind(
            "<Configure>",
            lambda e: self._list_canvas.config(
                scrollregion=self._list_canvas.bbox("all")
            ),
        )
        self._list_canvas.bind("<MouseWheel>", self._on_mousewheel)
        self._check_frame.bind("<MouseWheel>", self._on_mousewheel)

        self._check_vars: Dict[str, tk.BooleanVar] = {}
        self._check_widgets: List[Tuple[str, ttk.Checkbutton]] = []
        for label, _ in self._all_traces:
            var = tk.BooleanVar(value=True)
            var.trace_add("write", lambda *_, lbl=label: self._on_check(lbl))
            cb = ttk.Checkbutton(self._check_frame, text=label, variable=var)
            cb.pack(anchor=tk.W, padx=4, pady=1)
            self._check_vars[label] = var
            self._check_widgets.append((label, cb))
            cb.bind("<MouseWheel>", self._on_mousewheel)

        # Select / Clear buttons
        btn_row = ttk.Frame(left)
        btn_row.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(
            btn_row, text="Select All", command=self._select_all
        ).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 2))
        ttk.Button(
            btn_row, text="Clear All", command=self._clear_all
        ).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(2, 0))

    def _build_right_panel(self) -> None:
        right = ttk.Frame(self.root)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self._fig = Figure(tight_layout=True)
        self._ax  = self._fig.add_subplot(111)

        self._canvas_plot = FigureCanvasTkAgg(self._fig, master=right)
        self._canvas_plot.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        toolbar = NavigationToolbar2Tk(self._canvas_plot, right)
        toolbar.update()
        toolbar.pack(fill=tk.X)

    # ── event handlers ────────────────────────────────────────────

    def _on_mousewheel(self, event: tk.Event) -> None:
        self._list_canvas.yview_scroll(-1 * (event.delta // 120), "units")

    def _on_filter_change(self) -> None:
        visible = set(self._visible_labels())
        for label, cb in self._check_widgets:
            cb.pack_forget()
        for label, cb in self._check_widgets:
            if label in visible:
                cb.pack(anchor=tk.W, padx=4, pady=1)
        self._list_canvas.update_idletasks()
        self._list_canvas.config(scrollregion=self._list_canvas.bbox("all"))

    def _on_check(self, label: str) -> None:
        self._checked[label] = self._check_vars[label].get()
        self._refresh_plot()

    def _select_all(self) -> None:
        for lbl in self._visible_labels():
            self._check_vars[lbl].set(True)

    def _clear_all(self) -> None:
        for lbl in self._visible_labels():
            self._check_vars[lbl].set(False)

    # ── helpers ───────────────────────────────────────────────────

    def _visible_labels(self) -> List[str]:
        filt = self._filter.get().lower()
        return [lbl for lbl, _ in self._all_traces if filt in lbl.lower()]

    def _parse_range(self) -> Tuple:
        def _try(s):
            try:
                return float(s.strip()) if s.strip() else None
            except ValueError:
                return None

        return _try(self._x_min.get()), _try(self._x_max.get())

    # ── plot refresh ──────────────────────────────────────────────

    def _refresh_plot(self) -> None:
        x_col = self._x_col.get()
        y_col = self._y_col.get()
        if not x_col or not y_col or x_col == y_col:
            return

        xmin, xmax = self._parse_range()
        self._ax.cla()

        prop_cycle = plt.rcParams["axes.prop_cycle"]
        colors = [p["color"] for p in prop_cycle]
        color_idx = 0
        any_plotted = False

        for label, data in self._all_traces:
            if not self._checked.get(label):
                continue
            x = data.get(x_col)
            y = data.get(y_col)
            if x is None or y is None:
                continue

            mask = np.ones(len(x), dtype=bool)
            if xmin is not None:
                mask &= x >= xmin
            if xmax is not None:
                mask &= x <= xmax

            color = colors[color_idx % len(colors)]
            color_idx += 1
            self._ax.plot(x[mask], y[mask], label=label, color=color, linewidth=1.2)
            any_plotted = True

        self._ax.set_xlabel(x_col)
        self._ax.set_ylabel(y_col)
        self._ax.set_title(f"{y_col}  vs  {x_col}")
        self._ax.grid(True, alpha=0.3, linestyle="--")

        if any_plotted:
            self._ax.legend(
                loc="best",
                fontsize="x-small",
                framealpha=0.7,
                ncol=max(1, color_idx // 20),  # wrap legend into columns if many traces
            )

        self._canvas_plot.draw()


# ── public entry-point ────────────────────────────────────────────


def launch(traces: TraceList, title: str = "") -> None:
    """
    Open the plotter window and block until it is closed.

    *traces* is a list of ``(label, data_dict)`` pairs where *data_dict*
    maps column names (strings) to 1-D ``np.ndarray`` values.
    The first column is used as the default x-axis.
    """
    root = tk.Tk()
    MDIFPlotterApp(root, traces, title=title)
    root.mainloop()
