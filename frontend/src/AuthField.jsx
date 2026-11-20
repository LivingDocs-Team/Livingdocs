import Icon from './icons';

/** Label + input with a leading icon, used by the Login and Register cards. Props go to the <input>. */
export default function AuthField({ id, label, icon, ...inputProps }) {
  return (
    <div className="auth-field">
      <label htmlFor={id}>{label}</label>
      <div className="auth-input">
        {icon && <Icon name={icon} />}
        <input id={id} {...inputProps} />
      </div>
    </div>
  );
}
