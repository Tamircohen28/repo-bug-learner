// Negative corpus.

declare function save(x: any): void;
declare const isoString: string;
declare const epoch: number;
declare const businessTz: string;
declare const dayjs: any;

// 1. Explicit ISO string
export function n1() {
  save({ id: 'a', scheduledAt: '2026-01-01T00:00:00Z' });
}

// 2. Date from epoch number
export function n2() {
  save({ id: 'b', startTime: new Date(1234567890000) });
}

// 3. UTC date constructor
export function n3() {
  save({ id: 'c', endTime: new Date(Date.UTC(2026, 0, 1)) });
}

// 4. tz-aware via dayjs.tz
export function n4() {
  save({ id: 'd', bookingDate: dayjs.tz(isoString, businessTz).toDate() });
}

// 5. ISO string variable
export function n5() {
  save({ id: 'e', appointmentTime: isoString });
}

// 6. Field name is unrelated — `createdAt` not in pattern
export function n6() {
  save({ id: 'f', createdAt: new Date() });
}

// 7. Field name `updatedAt` not in pattern
export function n7() {
  save({ id: 'g', updatedAt: new Date() });
}

// 8. Field name `loggedAt` not in pattern
export function n8() {
  save({ id: 'h', loggedAt: new Date() });
}

// 9. ISO string for slotStart
export function n9() {
  save({ id: 'i', slotStart: '2026-05-21T10:00:00Z' });
}

// 10. Date.UTC constructor for eventStart
export function n10() {
  save({ id: 'j', eventStart: new Date(Date.UTC(2026, 4, 21, 10)) });
}

// 11. epoch for eventEnd
export function n11() {
  save({ id: 'k', eventEnd: new Date(epoch) });
}

// 12. typed Date variable already
export function n12() {
  const ts: Date = new Date(Date.UTC(2026, 0, 1));
  save({ id: 'l', scheduledAt: ts });
}
