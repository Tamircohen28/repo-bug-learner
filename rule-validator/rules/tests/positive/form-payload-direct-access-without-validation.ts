// Positive corpus: the rule's metavariable-regex (`(?i)^([a-z][a-z0-9]*)?(submission|formpayload|intakeform)$`)
// Now case-insensitive on the suffix, matching:
// - bare: submission, Submission, formPayload, FormPayload, intakeForm, IntakeForm
// - prefixed: bookingSubmission, customerFormPayload, customerIntakeForm, etc.
// We cover 15+ distinct positives via different surrounding contexts.

type Sub = { fields: any; formFields: any };

export function f1(submission: Sub) {
  // ruleid: form-payload-direct-access-without-validation
  return submission.fields.email;
}

export function f2(submission: Sub) {
  // ruleid: form-payload-direct-access-without-validation
  return submission.formFields.name;
}

export function f3(formPayload: Sub) {
  // ruleid: form-payload-direct-access-without-validation
  return formPayload.fields.address;
}

export function f4(formPayload: Sub) {
  // ruleid: form-payload-direct-access-without-validation
  return formPayload.formFields.phone;
}

export function f5(intakeForm: Sub) {
  // ruleid: form-payload-direct-access-without-validation
  return intakeForm.fields.notes;
}

export function f6(intakeForm: Sub) {
  // ruleid: form-payload-direct-access-without-validation
  return intakeForm.formFields.zip;
}

export function f7(submission: Sub) {
  // ruleid: form-payload-direct-access-without-validation
  const v = submission.fields.bday;
  return v;
}

export function f8(formPayload: Sub) {
  // ruleid: form-payload-direct-access-without-validation
  const x = formPayload.fields.title;
  console.log(x);
  return x;
}

export function f9(intakeForm: Sub) {
  // ruleid: form-payload-direct-access-without-validation
  console.log(intakeForm.formFields.lineItem);
  return intakeForm.formFields.lineItem;
}

export function f10(submission: Sub) {
  // ruleid: form-payload-direct-access-without-validation
  if (true) {
    return submission.fields.amount;
  }
}

export function f11(formPayload: Sub) {
  // ruleid: form-payload-direct-access-without-validation
  const data = { value: formPayload.fields.role };
  return data;
}

export function f12(intakeForm: Sub) {
  // ruleid: form-payload-direct-access-without-validation
  return [intakeForm.formFields.slot];
}

export function f13(bookingSubmission: Sub) {
  // ruleid: form-payload-direct-access-without-validation
  return bookingSubmission.fields.date;
}

export function f14(customerFormPayload: Sub) {
  // ruleid: form-payload-direct-access-without-validation
  return customerFormPayload.formFields.street;
}

export function f15(appointmentIntakeForm: Sub) {
  // ruleid: form-payload-direct-access-without-validation
  return appointmentIntakeForm.fields.time;
}
