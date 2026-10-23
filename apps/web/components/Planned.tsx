export function Planned({ title, phase, summary }: { title: string; phase: string; summary: string }) {
  return (
    <section>
      <h1 className="text-2xl font-semibold">{title}</h1>
      <p className="mt-2 max-w-xl text-sm text-slate-600">{summary}</p>
      <p className="mt-4 inline-block rounded-md border border-amber-300 bg-amber-50 px-3 py-1.5 text-sm text-amber-900">
        Not implemented yet — scheduled for {phase}. This screen has no data or actions.
      </p>
    </section>
  );
}
