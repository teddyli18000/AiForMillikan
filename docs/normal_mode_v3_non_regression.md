# Normal Mode V3 Non-Regression Contract

This document is the implementation checklist for adding Normal balance-fall mode
without replacing the existing Experimental application.

## Preserved Experimental Shell

| Item | Automated test | Manual evidence | Screenshot/log |
| --- | --- | --- | --- |
| Original SplashScreen exists | `apps/desktop/tests/App.test.tsx` | Launch packaged EXE | `evidence/splash.png` |
| Original splash animation remains | `apps/desktop/tests/App.test.tsx` checks animated field classes | Launch packaged EXE | `evidence/splash_animation.png` |
| TopBar remains available in Experimental | `apps/desktop/tests/App.test.tsx` | Enter Experimental | `evidence/experimental_topbar.png` |
| Experimental setup remains | `apps/desktop/tests/App.test.tsx` | Enter setup | `evidence/experimental_setup.png` |
| Experimental analysis remains | `apps/desktop/tests/App.test.tsx` | Run existing analysis path | `evidence/experimental_analysis.png` |
| Experimental results remain | `apps/desktop/tests/App.test.tsx` | Open results | `evidence/experimental_results.png` |
| Experimental export remains | `apps/desktop/tests/App.test.tsx` | Export report | `evidence/experimental_export.log` |
| Load run remains | `apps/desktop/tests/App.test.tsx` | Open run directory | `evidence/load_run.log` |

## New Safety Requirements

| Item | Automated test | Manual evidence | Screenshot/log |
| --- | --- | --- | --- |
| Production has no demo API fallback | `apps/desktop/tests/App.test.tsx` | Packaged startup without preload failure | `evidence/no_demo_fallback.log` |
| Normal mode state is isolated | `apps/desktop/tests/App.test.tsx` | Switch modes after measuring | `evidence/mode_isolation.png` |
| Experimental state is isolated | `apps/desktop/tests/App.test.tsx` | Switch back to Experimental | `evidence/experimental_state.png` |
| Normal mode uses progressive disclosure | `apps/desktop/tests/App.test.tsx` | Complete staged workflow | `evidence/normal_progressive.png` |
| Invalid q can only be diagnostic | `tests/test_normal_mode.py` | Save invalid record | `evidence/diagnostic_record.png` |
| Packaged resources are self-contained | `apps/desktop/tests/App.test.tsx` plus package audit | Launch without dev env | `evidence/package_resource_audit.log` |

## Completion Standard

Passing tests, generating an EXE, or starting the app is not completion by itself.
Completion requires a packaged GUI E2E showing real frame selection, synchronized
overlay review, true crossing loop playback, scientific quality gates, automatic
session recovery, eligible inversion or a clearly labeled QA fixture session,
Experimental non-regression, and zero external runtime dependencies.
