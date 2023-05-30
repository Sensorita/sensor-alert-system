# sensor-alert-system
Automatic alers when sensors do not send data

The system runs on an ec2 instance (same one as the dashboard) in the AWS Account: 9832 1132 3883

To ssh into the instance move to the directory holding your `dashboard-login.pem` file and use:
```
ssh -i "dashboard-login.pem" ec2-user@ec2-52-16-45-158.eu-west-1.compute.amazonaws.com
```

The instance is running on the TMUX session SensorAlertSystem