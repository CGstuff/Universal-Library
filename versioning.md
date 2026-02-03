# Universal Asset Library (UAL)
## Blender Studio Workflow — Role-Based & Representation-Driven Assets

This document defines a Blender-first asset workflow designed to support
multi-artist collaboration **without USD**, while preserving USD-like safety,
traceability, and scalability.

The system combines:
- Role-based asset ownership
- Multiple representations per asset
- Clear authority boundaries
- Controlled visibility of WIP data

---

## 1. Core Principle

> **Assets do not grow linearly.  
> Assets accumulate authority through representations.**

Only **final representations** are production-authoritative.
All other representations exist as dependencies or history.

---

## 2. Asset Definition (Logical Entity)

An asset is a logical container with:
- A single persistent asset UUID
- Multiple representations
- Independent versioning per representation
- A single production-approved output

Example:
Asset: Character_A
├── Representation: Model
├── Representation: Lookdev
└── Representation: Rig (FINAL)


---

## 3. Role-Based Responsibilities

Each representation has a single owner role.

| Role | Representation | Authority |
|----|---------------|----------|
| Modeler | Model | Geometry topology |
| Texture Artist | Lookdev | Materials & textures |
| Rigger | Rig | Deformation & controls |

Rules:
- Roles **do not modify upstream representations**
- Each role consumes previous representations via linking
- Authority flows downstream only

---

## 4. Representation Rules

### 4.1 Model Representation
**Purpose:** Geometry authority

- Contains:
  - Meshes
  - Naming conventions
  - Applied transforms
- Does NOT contain:
  - Materials
  - Textures
  - Rigging
- Versioned independently

File example:
CharacterA_model_v003.blend


---

### 4.2 Lookdev Representation
**Purpose:** Material authority

- Links geometry from Model representation
- Contains:
  - Materials
  - Texture nodes
  - UV usage
- Does NOT modify geometry
- Does NOT include rigging

File example:
CharacterA_lookdev_v002.blend


---

### 4.3 Rig Representation (Final Output)
**Purpose:** Production-ready asset

- Links:
  - Geometry from Model
  - Materials from Lookdev
- Contains:
  - Armature
  - Constraints
  - Deformation logic
- This is the **only representation used in shots**

File example:

CharacterA_rig_v001.blend

---

## 5. Versioning Rules

Versioning applies **per representation**, not per asset.

Rules:
- Versions are immutable
- New publish = new version
- Previous versions remain accessible but hidden by default
- Only one version per representation can be marked as “current”

Example:

CharacterA_model_v001
CharacterA_model_v002
CharacterA_model_v003 (current)

CharacterA_lookdev_v001
CharacterA_lookdev_v002 (current)

CharacterA_rig_v001 (current, FINAL)

---

## 6. Production Authority Rules

Only assets that meet **all** of the following are production-approved:

- Representation type == Rig
- Status == Approved
- Dependencies are valid
- Validation checks pass

All other representations are:
- WIP
- Hidden from shot assembly
- Non-selectable by default

---

## 7. Asset Library Visibility Rules (UAL Behavior)

### 7.1 Default User View
Artists see:

Character_A (FINAL)


They do NOT see:
- Model representation
- Lookdev representation
- Historical versions

---

### 7.2 Advanced / TD View
TDs can:
- Browse representations
- Inspect dependency graphs
- Roll back versions
- Promote or demote representations

---

## 8. Dependency Graph Rules

Dependencies flow strictly downstream:

Model → Lookdev → Rig



Rules:
- Downstream representations link upstream data
- Upstream representations are read-only
- Broken links block publishing

---

## 9. Override Rules

Overrides are never embedded in assets.

Allowed:
- Scene-level overrides
- Shot-level overrides
- User-local overrides

Overrides may affect:
- Materials
- Visibility
- Transform offsets

Overrides must be:
- External
- Reversible
- Non-destructive

---

## 10. Validation Checks (Pre-Publish)

Before publishing any representation:

- [ ] File opens without errors
- [ ] Geometry naming valid
- [ ] Scale & axis correct
- [ ] Dependencies resolved
- [ ] No forbidden data present
- [ ] Representation role respected

Failure blocks publish.

---

## 11. Failure Recovery & Rollback

Because representations are independent:
- Model changes do not destroy rigs
- Lookdev changes do not destroy geometry
- Rig changes do not affect upstream data

Rollback is done by:
- Switching representation version
- Never editing history

---

## 12. Storage & Bloat Policy

Data duplication is acceptable.

Rules:
- Bloat is controlled via visibility
- Only final representations are user-facing
- Storage cost is cheaper than pipeline risk

This mirrors real studio practice.

---

## 13. Blender-Specific Implementation Notes

Recommended:
- Use Blender library linking for upstream data
- Lock linked data
- Enforce read-only behavior in UI
- Prevent destructive appends unless explicitly requested

---

## 14. Summary

This workflow provides:
- USD-like safety without USD
- Clear ownership boundaries
- Parallel artist workflows
- Minimal conflict risk
- Predictable production behavior

**UAL enforces structure.  
Artists gain speed without risking integrity.**

---

## 15. Cold Storage Policy (Explicit)

Cold storage is a **first-class concept** in the UAL workflow.

### Definition
Cold storage refers to asset representations or versions that are:
- Non-authoritative
- Non-browsable by default
- Not loadable into shots
- Retained for rollback, auditing, and recovery

Cold assets are not deleted or flattened.

---

### What Goes to Cold Storage
The following are automatically placed in cold storage:

- Superseded versions of any representation
- WIP representations (Model, Lookdev)
- Deprecated or demoted representations
- Historical publish states

---

### Visibility Rules
| User Type | Cold Assets Visible |
|---------|---------------------|
| Artist | ❌ |
| Lead / TD | ✅ |
| System | ✅ |

---

### Mutability Rules
Cold assets are:
- Read-only
- Immutable
- Protected from overwrite

They may only be:
- Inspected
- Promoted to active
- Restored as current

---

### Rationale
Cold storage prioritizes:
- Pipeline safety
- Rollback capability
- Auditability
- Non-destructive iteration

Storage cost is accepted as a trade-off for production stability.
