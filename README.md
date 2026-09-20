FarewellPass is a ticketing system designed for managing entry to a farewell event. Attendees can purchase a ticket by entering their name and will receive a unique QR code associated with their ticket.
Features
Ticket Purchase — Attendees can purchase tickets by providing their name.
Unique QR Code — Each purchased ticket generates a unique QR code.
Host Dashboard — A secure dashboard accessible only with authorized credentials.
Purchase Records — Hosts can view and manage ticket purchase records.
Entry Logs — The dashboard maintains a record of scanned and verified tickets.
Built-in QR Scanner — QR codes can be scanned and verified directly through the host dashboard.
Customization
Background images and text can be customized by editing their respective files.
All image assets are stored in the static folder.

Environment Variables
The project uses environment variables to store host credentials and other sensitive configuration.
Create a .env file in the project's root directory and add the required credentials.

Note: Do not commit the .env file to version control. Add it to .gitignore to keep sensitive credentials private.
Deployment
FarewellPass is currently configured to run on a local host for development and testing.
It can also be configured for deployment on a public host when required. Additional configuration may be necessary depending on the hosting environment.

Future Updates
Minor updates and improvements may be added to the project in the future.
