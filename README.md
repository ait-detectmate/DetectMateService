# DetectMate Service

![UML](docs/img/logo_2.svg)

DetectMate Service is a framework for building modular log processing and anomaly detection services that
communicate via [NNG](https://nng.nanomsg.org/) messaging. Each service runs one component (for example a
parser or detector from [DetectMateLibrary](https://github.com/ait-detectmate/DetectMateLibrary)), receives
data on an input socket, forwards the results to one or more output sockets, and exposes an HTTP API for
management and Prometheus metrics.

## Documentation

- [Library Documentation](https://ait-detectmate.github.io/DetectMateLibrary/latest/)
- [Service Documentation](https://ait-detectmate.github.io/DetectMateService/latest) (this repo)

## Contribution

We're happily taking patches and other contributions. Please see the following links for how to get started:

- [Git Workflow](https://ait-detectmate.github.io/DetectMateService/latest/contribution/)
- [Development](https://ait-detectmate.github.io/DetectMateService/latest/development/)

If you encounter any bugs, please create an issue on [GitHub](https://github.com/ait-detectmate/DetectMateService/issues).

## License

[EUPL-1.2](https://github.com/ait-detectmate/DetectMateService/blob/main/LICENSE.md)
