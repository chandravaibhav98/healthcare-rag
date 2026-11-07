/**
 * Phase 0 shell. Phase 6 replaces it with the router, the Query Assistant and the
 * Admin Dashboard. The clinical disclaimer is a permanent requirement (risk R8),
 * so it ships from the very first build.
 */
export function App() {
  return (
    <main>
      <div role="alert" data-testid="clinical-disclaimer">
        <strong>Not for clinical use.</strong> All guideline content is synthetic.
      </div>
      <h1>Healthcare Guidelines RAG Assistant</h1>
      <p>Citation-first, evidence-validated answers from guideline documents.</p>
    </main>
  );
}
