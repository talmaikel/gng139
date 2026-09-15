/** @type {import('next').NextConfig} */
const API_ORIGIN = process.env.API_ORIGIN ?? "http://127.0.0.1:8000";

const nextConfig = {
  // react-leaflet v4's MapContainer doesn't clean up its Leaflet instance
  // correctly under React 18 Strict Mode's dev-only double-invoked effects,
  // which throws "Map container is already initialized" on every mount.
  reactStrictMode: false,

  // ── מקור אחד לדפדפן ──
  //
  // הדפדפן פנה עד כה ישירות ל-`localhost:8000`, ולכן האפליקציה עבדה
  // **רק על המחשב שמריץ אותה**. פתיחה ממחשב אחר, מטלפון, או דרך מנהרה
  // נתנה מסך שנטען ובקשות שנכשלות — בלי שגיאה שמסבירה למה.
  //
  // עכשיו הדפדפן מדבר עם מקור אחד בלבד, ו-Next מעביר הלאה. זה גם מבטל
  // את CORS: אין יותר בקשות חוצות-מקור, ולכן גם אין רשימת מקורות מותרים
  // שצריך לזכור לעדכן.
  // ‏S1 · סריקה שמוסרת עד שלושה תיקים שולפת עד שני תיקי בניין מהארכיון,
  // 10–20 שניות כל אחד. ברירת המחדל של ה-proxy היא 30 שניות, ובקשה
  // ארוכה ממנה הייתה נקטעת אחרי שהמסירה כבר בוצעה — הלקוח היה רואה שגיאה
  // על תיקים שכבר קיבל.
  experimental: { proxyTimeout: 90_000 },

  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_ORIGIN}/api/:path*` }];
  },
};

module.exports = nextConfig;
