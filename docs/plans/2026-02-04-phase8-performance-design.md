# Phase 8: Performance Optimization Design

## Goal

Fix the worst performance bottlenecks with reasonable effort. Accept some limitations of the Python+Qt stack rather than pursuing maximum performance.

**Non-goal:** Matching Rust version responsiveness. That can be phase 9/10 if needed.

## Bottlenecks Addressed

| Issue | Root Cause | Solution |
|-------|-----------|----------|
| White window on startup | All tabs init before `show()` | Deferred window show |
| Graph UI degradation | 4 graphs updating every 500ms | Pause when hidden + simplify rendering |
| Tab switch hangs | Subprocess calls take 5-30s | Targeted lazy loading with loading overlays |
| Resize freezes on static tabs | Unknown - needs profiling | Profile then simplify |

---

## 1. Startup Experience (Deferred Window Show)

### Current Flow
```
QApplication() → MainWindow() → [all tabs init] → window.show() → [white window] → prewarm_caches() → [content appears]
```

### New Flow
```
QApplication() → MainWindow(hidden) → [all tabs init] → prewarm_caches() → [wait for critical content] → window.show() → [fully rendered]
```

### Implementation

1. **Don't call `window.show()` in main.py** until initialization complete
2. **Define critical content** (must load before showing):
   - System info header (CPU name, memory, OS version)
   - Overview tab metrics (first data point)
   - Sidebar navigation ready
3. **Non-critical content** loads after show:
   - Software table
   - Startup apps table
   - Other tab data (already deferred)
4. **Add signal** `MainWindow.ready_to_show` emitted when critical content loaded
5. **Timeout fallback** - show window after 5s max even if not everything loaded

---

## 2. Graph Performance (Pause + Simplify)

### Visibility-Aware Updates

- Track whether Overview tab is active via `QStackedWidget.currentChanged`
- When tab not visible: pause `LoopingWorker` for graph updates
- Resume when tab becomes visible again

### Resize-Aware Pausing

- On `resizeEvent` start: set flag to skip graph rendering
- Increase debounce timer from 50ms to 150ms
- On debounce timer fire: clear flag, do single batched update

### Rendering Simplifications

- Disable antialiasing: `pg.setConfigOptions(antialias=False)`
- Reduce stored points to ~60 (1 minute at 1s intervals)
- Use `downsample` and `clipToView` options on plot curves
- Set static axis ranges instead of auto-scaling

### Collapsed Tile Optimization

- When metric tile collapsed, pause its graph updates
- Only update visible/expanded graphs

---

## 3. Tab Switch Responsiveness (Targeted Lazy Loading)

### Principle

Keep tab structure eager, defer only data. Tables start empty with loading overlay, data fetched on first tab activation.

### Targeted Application

| Tab | Widget | Trigger |
|-----|--------|---------|
| DriversTab | Drivers table | First tab show |
| TaskSchedulerTab | Tasks table | First tab show |
| EnterpriseTab | Info cards | First tab show |

### Loading Overlay Pattern

- `LoadingOverlay` widget on each slow table (already exists)
- Shows spinner + "Loading..." text
- Hides when `DataCache.data_loaded` signal fires

### Tab Activation Detection

- Connect to `QStackedWidget.currentChanged`
- Each tab gets `on_tab_activated()` method
- First activation triggers data load, subsequent activations no-op

### Remove Unconditional Prewarm

- Currently `prewarm_caches()` triggers task scheduler load unconditionally
- Change to only prewarm critical Overview data
- Let other tabs load on-demand

---

## 4. Resize Performance (Profile + Simplify)

### Profiling Instrumentation

- Wrap `resizeEvent` handlers with timing logs
- Instrument `FlowLayout.doLayout()` to measure time per call
- Log widget count and nesting depth for slow tabs
- Track number of layout passes per resize drag

### Profiling Session

- Resize window while on each tab
- Identify which tabs/components take longest
- Document findings before making changes

### Likely Fix Candidates

- **FlowLayout**: Cache geometry calculations, skip recalc if size unchanged
- **InfoCard/EnterpriseCard**: Reduce internal widget count if excessive
- **Collapsible sections**: Disable animations during resize
- **ScrollArea**: Optimize `widgetResizable` behavior

### General Qt Optimizations

- `setAttribute(Qt.WA_StaticContents)` on static widgets
- Batch layout updates with `setUpdatesEnabled(False)` during resize
- Consider `setFixedHeight()` on rows that don't reflow

---

## Implementation Order

| # | Task | Dependency | Impact |
|---|------|------------|--------|
| 1 | Deferred window show | None | Fixes white window startup |
| 2 | Graph visibility pausing | None | Reduces CPU when not viewing Overview |
| 3 | Graph resize pausing | Task 2 | Fixes resize freezes on Overview |
| 4 | Graph rendering simplification | None | General graph performance |
| 5 | Targeted lazy loading (Drivers) | None | Fixes Drivers tab hang |
| 6 | Targeted lazy loading (Tasks) | None | Fixes Tasks tab hang |
| 7 | Targeted lazy loading (Enterprise) | None | Fixes Enterprise tab hang |
| 8 | Remove unconditional prewarm | Tasks 5-7 | Faster startup |
| 9 | Resize profiling | None | Identifies static tab freeze cause |
| 10 | Resize fixes | Task 9 | Fixes remaining resize issues |

**Parallelization:** Tasks 1-4 can run in parallel. Tasks 5-7 can run in parallel. Task 8 depends on 5-7. Task 10 depends on 9.

---

## Testing Approach

- Manual timing comparisons before/after each change
- Resize drag test on each tab
- Tab switch timing measurement
- Startup time measurement (hidden → shown)

---

## Out of Scope (Future Phases)

- Rust backend integration via FFI/PyO3
- Replacing subprocess calls with direct Windows API bindings
- Major architectural changes to threading model
- Switching UI frameworks
