import { redirect } from "next/navigation";

/** ‏W8 · מסך התמהיל הנפרד הוסר: התמהיל הוא חלק מהדוח הכלכלי, במחשבון התרחיש שבתיק
 *  (בקשה 12 של השותפים). קישור ישן מגיע לקטע הכלכלי. */
export default async function UnitMixPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  redirect(`/app/dossier/${id}#economics`);
}
