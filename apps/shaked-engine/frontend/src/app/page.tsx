import Link from "next/link";

export default function HomePage() {
  return (
    <main className="page">
      <div className="card" style={{ maxWidth: 480, margin: "3.5rem auto" }}>
        <p style={{ margin: 0, color: "#6b655c", fontSize: ".82rem", letterSpacing: ".08em" }}>
          חלופת שקד · הרצליה
        </p>
        <h1 style={{ margin: ".15rem 0 .8rem" }}>שקדן</h1>
        <p style={{ margin: "0 0 .6rem", lineHeight: 1.6 }}>
          איתור מגרשים להתחדשות עירונית במסלול חלופת שקד, לחברות יזמיות.
        </p>
        <p style={{ margin: "0 0 1.4rem", color: "#6b655c", fontSize: ".9rem", lineHeight: 1.6 }}>
          לכל מגרש יש תיק: הזכויות, תרחיש כלכלי, ומקור לכל מספר.
        </p>
        <Link
          href="/login"
          style={{
            display: "inline-block",
            borderRadius: 6,
            padding: "0.6rem 1.1rem",
            background: "#1f6f4f",
            color: "#fff",
            fontSize: "0.95rem",
            textDecoration: "none",
          }}
        >
          כניסה
        </Link>
      </div>
    </main>
  );
}
