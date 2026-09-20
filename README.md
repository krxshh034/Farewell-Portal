## Introduction
FarewellPass is a ticketing system designed to manage ticket purchases and event entry for a farewell event.
Attendees can purchase a ticket by entering their name and, after a successful payment, receive a unique QR code associated with their ticket.

Hosts can use the secure dashboard to manage purchase records, monitor entry logs, and verify tickets using the built-in QR scanner.
<br>

## Features 
🎟️ **Ticket Purchase —** Attendees can purchase tickets by providing their name.<br>
🔳 **Unique QR Code —** Each purchased ticket receives a unique QR code.<br>
💳 **Razorpay Integration —** Handles ticket payments through Razorpay.<br>
🔐 **Host Dashboard —** Secure dashboard accessible only with authorized credentials.<br>
📋 **Purchase Records —** Hosts can view and manage ticket purchase records.<br>
🚪 **Entry Logs —** Maintains a record of scanned and verified tickets.<br>
📷 **Built-in QR Scanner —** Allows hosts to scan and verify tickets directly from the dashboard.
<br>
## Tech Stack
Python<br>
Flask<br>
HTML<br>
CSS<br>
JavaScript<br>
Razorpay<br>
QR Code
<br>
## Customization
Background images and text can be customized by editing their respective files.
All image assets are stored in the static folder.
### Environment Variables<br>
Farewell Portal uses environment variables to store sensitive configuration such as host credentials and payment credentials.
Create a .env file in the project's root directory and add the required variables.<br>
**Example:**<br>
``` 
RAZORPAY_KEY_ID=your_key_id
RAZORPAY_KEY_SECRET=your_key_secret
HOST_USERNAME=your_username
HOST_PASSWORD=your_password
```
<br>

## Running Locally
Clone the repository and install the required dependencies:<br>

```
git clone <repository-url>
cd FarewellPass
pip install -r requirements.txt
```
Configure your .env file and then start the application:<br>
```
python app.py
```

The application is currently configured for local hosting and development.
<br>
## Deployment
FarewellPass is structured to be deployable on a public server.
Before deployment, configure:<br>
**Production Razorpay credentials,**
**Environment variables,**
**Server configuration.**
Additional configuration may be required depending on the hosting provider.
<br>

## Release
v1.0.0<br>
Initial stable release of FarewellPass.
See the Releases section for the current version.
<br>
## Future Updates
Minor updates, improvements, and additional features may be added in future releases.
