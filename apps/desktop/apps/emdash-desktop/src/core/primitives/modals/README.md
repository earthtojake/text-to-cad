# Modal primitive

Modals are renderer-only contributions. A modal definition combines its stable id, React
component, chrome configuration, caller props, and completion result:

```tsx
function ExampleModal({ title }: { title: string }) {
  const { complete, dismiss } = useModalController('exampleModal');
  return (
    <div>
      <p>{title}</p>
      <button onClick={() => complete(true)}>Continue</button>
      <button onClick={dismiss}>Cancel</button>
    </div>
  );
}

export const exampleModal = defineModal<boolean>()({
  id: 'exampleModal',
  component: ExampleModal,
  size: 'sm',
});
```

`defineModal` infers caller props from the component. The result type is explicit because it is
consumed by the modal controller and by the promise returned from `openModal`.

## Why this differs from views

Views have portable definitions and separate React runtimes because view refs are validated,
persisted, restored, and consumed by navigation without loading React components. Modals have no
rehydration or main-process representation, so their definition includes the component directly.

Modals use string ids as references rather than importing definitions at call sites:

```ts
const outcome = await openModal('exampleModal', { title: 'Continue?' });
```

The app-level modal API imports the catalog as a type only. This preserves full prop and result
inference while preventing modal-to-modal runtime import cycles and keeping component trees out of
callers and node-side tests. The manifest catalog is the single runtime aggregation point.

## Data and outcomes

Caller data remains ordinary React props. The modal store holds it opaquely and the renderer
spreads it onto the resolved component:

```tsx
<Component {...active.props} />
```

Completion is a separate host channel. Modal components use `useModalController(id)` to complete,
dismiss, or manage the close guard. The controller is supplied by `ModalRenderer` through
`ModalHostContext`; tests and stories can use `ModalHostTestProvider`.

`openModal` returns `Result<TResult, ModalDismissed>`, using the same expected-outcome pattern as
the rest of the application. Completion produces `{ success: true, data: result }`; dismissal
produces `{ success: false, error: { type: 'modal_dismissed', reason } }`. This guarantees that
callers awaiting a modal settle when a user cancels it, passively closes it, or navigation closes it.
Dismissal reasons are `explicit`, `passive`, or `navigation`.

Modals are stacked. Opening another modal keeps the current modal mounted underneath the new one,
and only the top modal responds to outside presses or close commands. If a completed or dismissed
modal opens its successor in the same turn, the store swaps the closing top entry without rendering
a closed frame.

## Invariants

- Modal ids are non-empty and unique in the catalog.
- Definitions and catalog tuples are frozen.
- Chrome values are declared on the definition; renderer defaults are not copied into defs.
- Application code imports the modal catalog as a type unless it is resolving a modal at runtime.
- Modal components receive data through props and host actions through the controller.
