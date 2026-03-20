pageTour([
  { selector: 'h1', title: 'Settings', text: 'Manage your profile, security settings, and public information from here.' },
  { selector: '#file-pick-btn', title: 'Profile Picture', text: 'Click Choose Image to upload a new avatar. A cropper will appear so you can frame it perfectly before saving.' },
  { selector: 'input[name="username"]', title: 'Username & Name', text: 'Update your username and full name. Your username is shown publicly across the platform.' },
  { selector: 'textarea[name="bio"]', title: 'Bio', text: 'Write a short bio about yourself. This is visible to anyone who views your public profile.' },
  { selector: 'input[name="github"]', title: 'Social Links', text: 'Add your GitHub, LinkedIn, Facebook, Discord, and contact number. All are optional and shown on your public profile.' },
  { selector: 'input[name="current_password"]', title: 'Change Password', text: 'To change your password, enter your current password and your new one. Leave blank to keep the current one.' },
], 'tour_settings');
