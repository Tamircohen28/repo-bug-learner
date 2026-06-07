// Negative corpus.

declare const staffRepository: any;
declare const staffMembersService: any;
declare const staffMembersAdapter: any;
declare const staffApi: any;
declare const membersRepository: any;
declare const ctx: any;

// 1. Passes appDefId
export function n1() {
  return staffRepository.list({ appDefId: 'abc', tenantId: 't' });
}

// 2. Passes applicationDefinitionId
export function n2() {
  return staffMembersService.query({ applicationDefinitionId: 'abc' });
}

// 3. Passes appId
export function n3() {
  return staffMembersAdapter.find({ appId: 'abc', scheduleId: 's' });
}

// 4. Receiver via ctx with appDefId
export function n4() {
  return ctx.staffApi.search({ appDefId: 'abc' });
}

// 5. ctx.staffRepository with appDefId
export function n5() {
  return ctx.staffRepository.fetch({ appDefId: 'abc' });
}

// 6. Receiver name NOT in allowlist — staffSectionSummary
declare const staffSectionSummary: any;
export function n6() {
  return staffSectionSummary.list({ tenantId: 't' });
}

// 7. Receiver name NOT in allowlist — staffAvailability
declare const staffAvailability: any;
export function n7() {
  return staffAvailability.query({ id: 'x' });
}

// 8. membersRepository — explicitly excluded
export function n8() {
  return membersRepository.list({ tenantId: 't' });
}

// 9. ctx.membersRepository — explicitly excluded
export function n9() {
  return ctx.membersRepository.find({ id: 'a' });
}

// 10. CRM members API name — not staff
declare const memberService: any;
export function n10() {
  return memberService.query({ tenantId: 't' });
}

// 11. Receiver with appDefId mixed in
export function n11() {
  return staffApi.search({ tenantId: 't', appDefId: 'x' });
}

// 12. Receiver with appId nested
export function n12() {
  return staffRepository.find({ appId: 'a', tenantId: 't' });
}
