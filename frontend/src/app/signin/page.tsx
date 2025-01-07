import { SigninForm } from './SigninForm';

export default function SignInPage() {
  return (
    <div className='min-h-screen bg-gray-50 flex flex-col justify-center py-12 sm:px-6 lg:px-8'>
      <div className='mx-4 xs:mx-auto xs:w-full xs:max-w-md'>
        <h2 className='mt-6 text-center text-3xl font-extrabold text-gray-900'>
          Sign in to SoarHigh
        </h2>
      </div>

      <div className='mt-8 mx-4 xs:mx-auto xs:w-full xs:max-w-md'>
        <div className='bg-white py-8 px-4 shadow xs:rounded-lg xs:px-10'>
          <SigninForm />
        </div>
      </div>
    </div>
  );
}
