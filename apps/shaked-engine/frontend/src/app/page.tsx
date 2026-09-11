import Link from "next/link";

export default function HomePage() {
  return (
    <main className="page">
      <h1>Shaked Engine</h1>
      <p>B2B urban-renewal opportunity screening under the Shaked Alternative (חלופת שקד).</p>
      <p>
        <Link href="/login">Sign in</Link> to view candidate opportunities.
      </p>
    </main>
  );
}
