// Negative corpus.

type Sub = { fields: any; formFields: any; isValid: boolean };

declare function validateForm(s: any): boolean;
declare function validateSubmissionForm(s: any): boolean;
declare function isValidSubmission(s: any): boolean;
declare function assertFormValid(s: any): boolean;
declare function verifyForm(s: any): boolean;
declare function checkForm(s: any): boolean;

// 1. Guarded by validateForm(...)
export function n1(submission: Sub) {
  if (validateForm(submission)) {
    return submission.fields.email;
  }
}

// 2. Guarded by validateSubmissionForm(...)
export function n2(formSubmission: Sub) {
  if (validateSubmissionForm(formSubmission)) {
    return formSubmission.fields.name;
  }
}

// 3. Guarded by isValidSubmission(...)
export function n3(formPayload: Sub) {
  if (isValidSubmission(formPayload)) {
    return formPayload.formFields.address;
  }
}

// 4. Guarded by assertFormValid(...)
export function n4(intakeForm: Sub) {
  if (assertFormValid(intakeForm)) {
    return intakeForm.fields.phone;
  }
}

// 5. Guarded by .isValid property
export function n5(submission: Sub) {
  if (submission.isValid) {
    return submission.fields.notes;
  }
}

// 6. Guarded by .isValid() method
export function n6(formPayload: Sub) {
  if (formPayload.isValid()) {
    return formPayload.formFields.zip;
  }
}

// 7. Variable name `user` doesn't match the regex
export function n7(user: Sub) {
  return user.fields.email;
}

// 8. Variable name `request` doesn't match
export function n8(request: Sub) {
  return request.formFields.email;
}

// 9. Variable name `data` doesn't match
export function n9(data: Sub) {
  return data.fields.email;
}

// 10. Variable name `payload` (no "form" prefix) — regex requires *FormPayload not just payload
export function n10(payload: Sub) {
  return payload.fields.x;
}

// 11. Guarded by verifyForm(...)
export function n11(memberSubmission: Sub) {
  if (verifyForm(memberSubmission)) {
    return memberSubmission.fields.role;
  }
}

// 12. Guarded by checkForm(...)
export function n12(orderSubmission: Sub) {
  if (checkForm(orderSubmission)) {
    return orderSubmission.formFields.qty;
  }
}

// 13. PascalCase variant `CustomerFormPayload` with guard
export function n13(CustomerFormPayload: Sub) {
  if (validateForm(CustomerFormPayload)) {
    return CustomerFormPayload.fields.email;
  }
}

// 14. Guarded by isValid property on a broad-match name
export function n14(bookingSubmission: Sub) {
  if (bookingSubmission.isValid) {
    return bookingSubmission.formFields.slot;
  }
}
