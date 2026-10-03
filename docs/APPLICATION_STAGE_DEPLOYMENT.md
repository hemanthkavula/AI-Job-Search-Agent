# Application Stage Deployment Ordering

1. Production discovery and resume generation run normally.
2. Production acceptance validates the ready queue.
3. The workflow counts ready application rows.
4. Browser runtime is installed only when count > 0.
5. `app.application_stage --submit` executes the guarded application loop.
6. Updated generated state is synchronized to the dashboard and uploaded as the cycle artifact.
