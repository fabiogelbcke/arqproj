// WhatsApp numbers (A44), read as the server reads them (backend/notifications/
// whatsapp.py, same cases in phone.cases.json): kept in international digits,
// shown as people write them.

/** International digits (5511987654321), or null for what isn't a mobile we can
 *  write to. A Brazilian mobile may come with or without +55; any other country
 *  needs its +. */
export function parsePhone(raw: string): string | null {
  const text = raw.trim();
  let digits = text.replace(/\D/g, "");
  if (text.startsWith("+") || text.startsWith("00")) {
    if (text.startsWith("00")) digits = digits.replace(/^00/, "");
    if (digits.startsWith("55")) return brazilian(digits.slice(2));
    return /^[1-9]\d{7,14}$/.test(digits) ? digits : null;
  }
  if (digits.length === 13 && digits.startsWith("55")) digits = digits.slice(2);
  return brazilian(digits.replace(/^0/, ""));
}

function brazilian(national: string): string | null {
  return /^[1-9][1-9]9\d{8}$/.test(national) ? `55${national}` : null;
}

/** "5511987654321" → "(11) 98765-4321"; another country's as +351 912345678. */
export function formatPhone(digits: string): string {
  const br = /^55(\d{2})(\d{5})(\d{4})$/.exec(digits);
  if (br) return `(${br[1]}) ${br[2]}-${br[3]}`;
  return `+${digits}`;
}
