"use client";

import { Carousel, type Embla } from "@mantine/carousel";
import {
  ActionIcon, Badge, Button, Card, Chip, Container, Divider, Group, MultiSelect,
  Paper, RangeSlider, SegmentedControl, Select, SimpleGrid, Stack, Stepper, Switch, Text, Title,
} from "@mantine/core";
import { useEffect, useMemo, useState } from "react";
import classes from "./design.module.css";

const PAGES = [
  { label: "פתיחה", desc: "Shaked Engine" },
  { label: "המוצר", desc: "במחשב ובטלפון" },
  { label: "איך זה עובד", desc: "ארבעה שלבים" },
  { label: "למה שקדן", desc: "נוחות, זמן, מידע" },
  { label: "צרו קשר", desc: "הדגמה ופרטים" },
];

const STEPS = [
  { title: "מסמנים אזור על המפה", text: "פוליגון חופשי, רחוב אחד, או כל העיר. כל חלקה בתוך האזור נכנסת לבדיקה.", out: "רשימת חלקות עם גוש/חלקה, שטח וקומות" },
  { title: "המנוע מסנן: תנאי הסף, ומה שחשוב לך", text: "כל תנאי סף של חלופת שקד נבדק בנפרד, ואז מסננים לפי הפרמטרים של הפרויקט.", out: "מצב לכל חלקה, עם הנימוק" },
  { title: "פותחים תיק לחלקה", text: "הזכויות, תקרת 400%, לוח הדירות הקיימות ותרחיש כלכלי עם הנחות גלויות.", out: "רווח יזמי ותקרת היטל השבחה" },
  { title: "מייצאים ומעבירים הלאה", text: "PDF לוועדה, אקסל למחלקת הכלכלה. אותם מספרים בדיוק כמו במסך.", out: "מקור ומועד לכל מספר בתיק" },
];

type Status = "deliverable" | "verify" | "measure" | "out";
type Row = { address: string; gush: string; area: number; floors: number; units: number | null; hood: string; status: Status };

// Example rows for the trial page: real Herzliya addresses, illustrative neighbourhoods.
const ROWS: Row[] = [
  { address: "אלוף יגאל אלון 40", gush: "6537 / 120", area: 1575, floors: 8, units: 44, hood: "נווה עמל", status: "deliverable" },
  { address: "הדר 19", gush: "6538 / 476", area: 907, floors: 8, units: 25, hood: "שיכון מפ״ם", status: "deliverable" },
  { address: "אלוף יגאל אלון 6", gush: "6529 / 43", area: 794, floors: 7, units: null, hood: "נווה עמל", status: "verify" },
  { address: "בוסל 12", gush: "6530 / 284", area: 794, floors: 8, units: null, hood: "הרצליה הצעירה", status: "measure" },
  { address: "לוין שמעון זאב 14", gush: "6535 / 95", area: 907, floors: 9, units: 18, hood: "נוה ישראל", status: "verify" },
  { address: "מלכין שרה 10", gush: "6538 / 252", area: 977, floors: 5, units: 12, hood: "שיכון מפ״ם", status: "verify" },
  { address: "כבוש העבודה 18", gush: "6536 / 386", area: 979, floors: 8, units: null, hood: "גליל ים", status: "out" },
];

const STATUS: Record<Status, { label: string; color: string }> = {
  deliverable: { label: "ניתן למסירה", color: "teal" },
  verify: { label: "דורש אימות", color: "almond" },
  measure: { label: "דורש מדידה", color: "almond" },
  out: { label: "לא במסלול", color: "gray" },
};

const THRESHOLDS = ["מועד ההיתר", "70% מגורים", "בוצע חיזוק", "מספר מבנים", "יוזמה קיימת"];

const Chevron = ({ d }: { d: string }) => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d={d} /></svg>
);

function PageDeck() {
  const [embla, setEmbla] = useState<Embla | null>(null);
  const [active, setActive] = useState(0);
  useEffect(() => {
    if (!embla) return;
    const onSelect = () => setActive(embla.selectedScrollSnap());
    embla.on("select", onSelect);
    return () => { embla.off("select", onSelect); };
  }, [embla]);

  return (
    <div className={classes.deckRow}>
      <Carousel
        orientation="vertical"
        height={420}
        slideSize="100%"
        slideGap={0}
        withControls={false}
        loop={false}
        getEmblaApi={setEmbla}
        styles={{ root: { borderRadius: 5, overflow: "hidden" } }}
      >
        {PAGES.map((p, i) => (
          <Carousel.Slide key={p.label}>
            <div
              className={classes.deckPage}
              style={i === 0
                ? { backgroundImage: "linear-gradient(to left, rgba(19,22,30,.85), rgba(19,22,30,.2)), url(/brand/herzliya.jpg)" }
                : { background: i % 2 ? "#13161E" : "#2A2E39" }}
            >
              <Text size="sm" c="almond.3" fw={600}>עמוד {i + 1} מתוך {PAGES.length}</Text>
              <Title order={2} c="white" style={{ fontSize: i === 0 ? "3rem" : "2rem" }}>
                {i === 0 ? <bdi>Shaked Engine</bdi> : p.label}
              </Title>
              <Text c="gray.4">{p.desc}</Text>
            </div>
          </Carousel.Slide>
        ))}
      </Carousel>

      <Paper withBorder p="md" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <Group justify="space-between">
          <Text fw={700} size="sm">דפדוף בין העמודים</Text>
          <Group gap={6}>
            <ActionIcon variant="default" radius="xl" aria-label="העמוד הקודם" disabled={active === 0} onClick={() => embla?.scrollPrev()}>
              <Chevron d="M6 15l6-6 6 6" />
            </ActionIcon>
            <ActionIcon variant="default" radius="xl" aria-label="העמוד הבא" disabled={active === PAGES.length - 1} onClick={() => embla?.scrollNext()}>
              <Chevron d="M6 9l6 6 6-6" />
            </ActionIcon>
          </Group>
        </Group>
        <Stepper active={active} onStepClick={(i) => embla?.scrollTo(i)} orientation="vertical" size="sm" iconSize={28} allowNextStepsSelect>
          {PAGES.map((p) => <Stepper.Step key={p.label} label={p.label} description={p.desc} />)}
        </Stepper>
      </Paper>
    </div>
  );
}

function HowItWorks() {
  return (
    <Paper withBorder p={{ base: "md", sm: "xl" }} pb={72}>
      <Carousel
        withIndicators
        loop={false}
        slideGap="xl"
        controlSize={38}
        classNames={{ indicator: classes.indicator, indicators: classes.indicators, control: classes.control }}
        styles={{ controls: { top: "auto", bottom: -54, justifyContent: "center", gap: 130 } }}
      >
        {STEPS.map((s, i) => (
          <Carousel.Slide key={s.title}>
            <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="xl">
              <Stack gap="sm">
                <Group gap="sm">
                  <span className={classes.num}>{i + 1}</span>
                  <Text c="dimmed" fw={600}>שלב {i + 1} מתוך 4</Text>
                </Group>
                <Title order={3}>{s.title}</Title>
                <Text c="dimmed">{s.text}</Text>
                {i === 1 && (
                  <Stack gap={6}>
                    <Group gap={6}><Text size="sm" fw={600} w={80}>תנאי הסף</Text>{THRESHOLDS.map((t) => <Badge key={t} variant="outline" color="gray">{t}</Badge>)}</Group>
                    <Group gap={6}><Text size="sm" fw={600} w={80}>סינון נוסף</Text>{["גודל מגרש", "קומות", "רוחב רחוב", "שכונה"].map((t) => <Badge key={t} variant="light">{t}</Badge>)}</Group>
                  </Stack>
                )}
                <Badge size="lg" variant="light" style={{ alignSelf: "flex-start", textTransform: "none", fontWeight: 600 }}>מקבלים: {s.out}</Badge>
              </Stack>
              <div className={classes.stepPic}>
                <svg viewBox="0 0 360 200" width="100%" style={{ display: "block", direction: "ltr" }} aria-hidden>
                  <rect width="360" height="200" fill="#EEF0F3" />
                  <g stroke="#D9DDE3" strokeWidth="2"><path d="M0 60h360M0 120h360M90 0v200M200 0v200M290 0v200" /></g>
                  <path d="M70 40 L250 55 L280 150 L120 170 Z" fill="#E8894A" fillOpacity={0.12 + i * 0.05} stroke="#E8894A" strokeWidth="3" strokeDasharray="8 6" />
                  <g fill="#E8894A">{[0, 1, 2, 3, 4].slice(0, 2 + i).map((k) => <rect key={k} x={110 + k * 30} y={80 + (k % 2) * 30} width="20" height="16" rx="2" />)}</g>
                </svg>
              </div>
            </SimpleGrid>
          </Carousel.Slide>
        ))}
      </Carousel>
    </Paper>
  );
}

function ProductFilters() {
  const [scope, setScope] = useState("all");
  const [passed, setPassed] = useState<string[]>(THRESHOLDS);
  const [area, setArea] = useState<[number, number]>([500, 2000]);
  const [floors, setFloors] = useState<[number, number]>([5, 10]);
  const [hoods, setHoods] = useState<string[]>([]);
  const [onlyDeliverable, setOnlyDeliverable] = useState(false);
  const [sort, setSort] = useState<string | null>("area");

  const rows = useMemo(() => ROWS
    .filter((r) => scope === "all" || (scope === "screened" ? r.status !== "out" : r.status === "verify" || r.status === "measure"))
    .filter((r) => r.area >= area[0] && r.area <= area[1])
    .filter((r) => r.floors >= floors[0] && r.floors <= floors[1])
    .filter((r) => hoods.length === 0 || hoods.includes(r.hood))
    .filter((r) => !onlyDeliverable || r.status === "deliverable")
    .sort((a, b) => sort === "area" ? b.area - a.area : sort === "floors" ? b.floors - a.floors : a.address.localeCompare(b.address, "he")),
  [scope, area, floors, hoods, onlyDeliverable, sort]);

  const reset = () => { setScope("all"); setArea([500, 2000]); setFloors([5, 10]); setHoods([]); setOnlyDeliverable(false); setPassed(THRESHOLDS); };

  return (
    <SimpleGrid cols={{ base: 1, md: 3 }} spacing="lg">
      <Paper withBorder p="lg" style={{ alignSelf: "start" }}>
        <Stack gap="lg">
          <Group justify="space-between">
            <Text fw={700}>סינון</Text>
            <Button variant="subtle" size="compact-sm" color="gray" onClick={reset}>איפוס</Button>
          </Group>
          <SegmentedControl fullWidth value={scope} onChange={setScope} data={[{ value: "all", label: "הכול" }, { value: "screened", label: "עוברים סינון" }, { value: "verify", label: "דורשים אימות" }]} />
          <Stack gap={8}>
            <Text size="sm" fw={600}>תנאי הסף שחייבים לעבור</Text>
            <Chip.Group multiple value={passed} onChange={setPassed}>
              <Group gap={6}>{THRESHOLDS.map((t) => <Chip key={t} value={t} size="xs" variant="outline">{t}</Chip>)}</Group>
            </Chip.Group>
          </Stack>
          <Divider label="סינון נוסף" labelPosition="right" />
          <Stack gap={4}>
            <Group justify="space-between"><Text size="sm" fw={600}>גודל מגרש</Text><Text size="xs" className={classes.mono}>{area[0].toLocaleString()}–{area[1].toLocaleString()} מ״ר</Text></Group>
            <RangeSlider min={200} max={3000} step={50} value={area} onChange={setArea} label={null} />
          </Stack>
          <Stack gap={4}>
            <Group justify="space-between"><Text size="sm" fw={600}>קומות קיימות</Text><Text size="xs" className={classes.mono}>{floors[0]}–{floors[1]}</Text></Group>
            <RangeSlider min={1} max={14} step={1} minRange={0} value={floors} onChange={setFloors} marks={[{ value: 4 }, { value: 8 }, { value: 12 }]} label={null} />
          </Stack>
          <MultiSelect label="שכונה" placeholder="כל השכונות" data={[...new Set(ROWS.map((r) => r.hood))]} value={hoods} onChange={setHoods} clearable searchable />
          <Switch label="רק ניתנים למסירה" checked={onlyDeliverable} onChange={(e) => setOnlyDeliverable(e.currentTarget.checked)} />
          <Select label="מיון" value={sort} onChange={setSort} allowDeselect={false} data={[{ value: "area", label: "שטח מגרש, מהגדול" }, { value: "floors", label: "קומות, מהגבוה" }, { value: "address", label: "כתובת, א–ת" }]} />
        </Stack>
      </Paper>

      <Stack gap="sm" style={{ gridColumn: "span 2" }}>
        <Group justify="space-between">
          <Text fw={700} size="lg">{rows.length} מועמדים</Text>
          <Text size="xs" c="dimmed">נתוני דוגמה</Text>
        </Group>
        {rows.map((r) => (
          <Card key={r.gush} withBorder padding="md">
            <Group justify="space-between" wrap="nowrap" align="flex-start">
              <Stack gap={2}>
                <Text fw={700}>{r.address}</Text>
                <Text size="sm" c="dimmed" className={classes.mono}>{r.gush}</Text>
                <Text size="sm" c="dimmed">{r.area.toLocaleString()} מ״ר · {r.floors} קומות{r.units ? ` · ${r.units} דירות` : ""} · {r.hood}</Text>
              </Stack>
              <Stack gap={8} align="flex-end">
                <Badge color={STATUS[r.status].color} variant="light">{STATUS[r.status].label}</Badge>
                <Group gap={6}>
                  <Button size="xs" variant="default">כל התוכניות</Button>
                  <Button size="xs">פתיחת התיק</Button>
                </Group>
              </Stack>
            </Group>
          </Card>
        ))}
        {rows.length === 0 && (
          <Paper withBorder p="xl"><Text ta="center" c="dimmed">אין מגרשים שעונים על הסינון. נסו להרחיב את טווח השטח או הקומות.</Text></Paper>
        )}
      </Stack>
    </SimpleGrid>
  );
}

export default function DesignTrialPage() {
  return (
    <div className={classes.shell} dir="rtl">
      <Container size="lg">
        <Stack gap={56}>
          <Stack gap={4}>
            <img src="/brand/shakdan-lockup.svg" alt="shakdan" width={138} height={34} style={{ alignSelf: "flex-start" }} />
            <Title order={1} mt="md">רכיבי Mantine בשפה של שקדן</Title>
            <Text c="dimmed">עמוד ניסיון: שלושת הרכיבים לפני שמכניסים אותם לדף הפתיחה ולמוצר.</Text>
          </Stack>

          <Stack gap="md">
            <Title order={2}>1 · דפדוף למעלה ולמטה בין העמודים</Title>
            <Text c="dimmed">גוררים או גוללים בתוך המסגרת, או לוחצים על שלב בצד.</Text>
            <PageDeck />
          </Stack>

          <Stack gap="md">
            <Title order={2}>2 · דפדוף ימינה ושמאלה · איך זה עובד</Title>
            <Text c="dimmed">חצים, נקודות, או גרירה. בגרירה מעבר לשלב האחרון הקרוסלה נמתחת וחוזרת.</Text>
            <HowItWorks />
          </Stack>

          <Stack gap="md">
            <Title order={2}>3 · הסינון והמוצר</Title>
            <Text c="dimmed">הסינון עובד על הרשימה בזמן אמת.</Text>
            <ProductFilters />
          </Stack>
        </Stack>
      </Container>
    </div>
  );
}
