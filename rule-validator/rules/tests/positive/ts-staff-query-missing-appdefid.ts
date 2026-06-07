// Positive corpus for ts-staff-query-missing-appdefid.

declare const staffRepository: any;
declare const staffMembersService: any;
declare const staffMembersAdapter: any;
declare const staffApi: any;
declare const ctx: any;

export function p1() {
  // ruleid: ts-staff-query-missing-appdefid
  return staffRepository.list({ tenantId: 't1' });
}

export function p2() {
  // ruleid: ts-staff-query-missing-appdefid
  return staffMembersService.query({ siteId: 's1' });
}

export function p3() {
  // ruleid: ts-staff-query-missing-appdefid
  return staffMembersAdapter.find({ scheduleId: 'sc1' });
}

export function p4() {
  // ruleid: ts-staff-query-missing-appdefid
  return staffApi.search({ name: 'x' });
}

export function p5() {
  // ruleid: ts-staff-query-missing-appdefid
  return ctx.staffRepository.fetch({ resourceId: 'r1' });
}

export function p6() {
  // ruleid: ts-staff-query-missing-appdefid
  return ctx.staffMembersService.getAll({ businessId: 'b' });
}

export function p7() {
  // ruleid: ts-staff-query-missing-appdefid
  return ctx.staffMembersAdapter.list({ size: 10 });
}

export function p8() {
  // ruleid: ts-staff-query-missing-appdefid
  return ctx.staffApi.query({ from: 0 });
}

export function p9() {
  // ruleid: ts-staff-query-missing-appdefid
  return staffRepository.findOne({ id: 's1' });
}

export function p10() {
  // ruleid: ts-staff-query-missing-appdefid
  return staffMembersService.update({ id: 'x', name: 'new' });
}

export function p11() {
  // ruleid: ts-staff-query-missing-appdefid
  return staffMembersAdapter.create({ name: 'new' });
}

export function p12() {
  // ruleid: ts-staff-query-missing-appdefid
  return staffApi.delete({ id: 'x' });
}
