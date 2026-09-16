import { AppHeader } from "@/components/brand/AppShell";
import { DossierSubNav } from "./subnav";

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
      <AppHeader />
      <div className="page" style={{ maxWidth: 1000 }}>
        <DossierSubNav id={id} />
        {children}
      </div>
    </>
  );
}
