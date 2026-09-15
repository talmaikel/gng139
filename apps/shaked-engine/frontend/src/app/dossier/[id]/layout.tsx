import Link from "next/link";

export default async function DossierLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <>
      <nav
        style={{
          maxWidth: 1000,
          margin: ".75rem auto 0",
          padding: "0 1rem",
          display: "flex",
          gap: ".9rem",
          fontSize: ".85rem",
        }}
      >
        <Link href={`/dossier/${id}`}>תיק הזדמנות</Link>
        <Link href={`/dossier/${id}/mix`}>תמהיל ורווחיות</Link>
        <Link href={`/dossier/${id}/units`}>אישור דירות קיימות</Link>
      </nav>
      {children}
    </>
  );
}
