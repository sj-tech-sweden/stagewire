// Owner context for job vs. venue base-rig entities.
//
// A job owner is the legacy job id (a string). A venue owner is an object
// `{ kind: 'venue', id }` that targets the venue's Standard Base Rig. The
// backend exposes identical response shapes for both, so the frontend graph
// stores and components only need to switch the URL base via `ownerBase`.

export function isVenueOwner(owner) {
  return !!owner && typeof owner === 'object' && owner.kind === 'venue';
}

export function ownerId(owner) {
  return isVenueOwner(owner) ? owner.id : owner;
}

export function ownerBase(owner) {
  if (isVenueOwner(owner)) {
    return `/venues/${owner.id}/rig`;
  }
  return `/jobs/${owner}`;
}

export function ownerLabel(owner) {
  return isVenueOwner(owner) ? 'venue' : 'job';
}
