// Positive corpus for calendar-scheduled-time-without-explicit-timezone.

declare function save(x: any): void;

export function p1() {
  // ruleid: calendar-scheduled-time-without-explicit-timezone
  save({ id: 'a', scheduledAt: new Date(), tz: 'UTC' });
}

export function p2() {
  // ruleid: calendar-scheduled-time-without-explicit-timezone
  save({ id: 'b', startTime: new Date(), endTime: 'x' });
}

export function p3() {
  // ruleid: calendar-scheduled-time-without-explicit-timezone
  save({ id: 'c', endTime: new Date(), x: 1 });
}

export function p4() {
  // ruleid: calendar-scheduled-time-without-explicit-timezone
  save({ id: 'd', bookingDate: new Date(), x: 2 });
}

export function p5() {
  // ruleid: calendar-scheduled-time-without-explicit-timezone
  save({ id: 'e', appointmentTime: new Date(), n: 'q' });
}

export function p6() {
  // ruleid: calendar-scheduled-time-without-explicit-timezone
  save({ id: 'f', eventStart: new Date(), m: 'm' });
}

export function p7() {
  // ruleid: calendar-scheduled-time-without-explicit-timezone
  save({ id: 'g', eventEnd: new Date(), n: 'n' });
}

export function p8() {
  // ruleid: calendar-scheduled-time-without-explicit-timezone
  save({ id: 'h', slotStart: new Date(), n: 'n' });
}

export function p9() {
  // ruleid: calendar-scheduled-time-without-explicit-timezone
  save({ id: 'i', slotEnd: new Date(), n: 'n' });
}

export function p10() {
  // ruleid: calendar-scheduled-time-without-explicit-timezone
  const payload = { id: 'j', scheduledAt: new Date(), more: true };
  save(payload);
}

export function p11() {
  // ruleid: calendar-scheduled-time-without-explicit-timezone
  return { id: 'k', startTime: new Date(), endTime: 'x' };
}

export function p12() {
  // ruleid: calendar-scheduled-time-without-explicit-timezone
  return { id: 'l', appointmentTime: new Date() };
}
