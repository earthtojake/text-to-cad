import { createFormHook } from '@tanstack/react-form';
import { SubmitButton } from './components/submit-button';
import { ComboboxSelectField } from './fields/combobox-select-field';
import { NumberField } from './fields/number-field';
import { RadioGroupField } from './fields/radio-group-field';
import { SelectField } from './fields/select-field';
import { SwitchField } from './fields/switch-field';
import { TextField } from './fields/text-field';
import { TextareaField } from './fields/textarea-field';
import { fieldContext, formContext } from './form-context';

export const { useAppForm, withForm } = createFormHook({
  fieldContext,
  formContext,
  fieldComponents: {
    TextField,
    NumberField,
    RadioGroupField,
    TextareaField,
    SelectField,
    ComboboxSelectField,
    SwitchField,
  },
  formComponents: {
    SubmitButton,
  },
});
