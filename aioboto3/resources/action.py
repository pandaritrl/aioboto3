import logging

from boto3.resources.action import ServiceAction
from boto3.resources.params import create_request_parameters
from botocore import xform_name

from aioboto3.resources.response import AIOResourceHandler, AIORawHandler

logger = logging.getLogger(__name__)


class AioBatchAction(ServiceAction):
    """
    An action which operates on a batch of items in a collection, typically
    a single page of results from the collection's underlying service
    operation call. For example, this allows you to delete up to 999
    S3 objects in a single operation rather than calling ``.delete()`` on
    each one individually.

    :type action_model: :py:class`~boto3.resources.model.Action`
    :param action_model: The action model.

    :type factory: ResourceFactory
    :param factory: The factory that created the resource class to which
                    this action is attached.

    :type service_context: :py:class:`~boto3.utils.ServiceContext`
    :param service_context: Context about the AWS service
    """
    async def __call__(self, parent, *args, **kwargs):
        """
        Perform the batch action's operation on every page of results
        from the collection.

        :type parent:
            :py:class:`~boto3.resources.collection.ResourceCollection`
        :param parent: The collection iterator to which this action
                       is attached.
        :rtype: list(dict)
        :return: A list of low-level response dicts from each call.
        """
        service_name = None
        client = None
        responses = []
        operation_name = xform_name(self._action_model.request.operation)

        # Unlike the simple action above, a batch action must operate
        # on batches (or pages) of items. So we get each page, construct
        # the necessary parameters and call the batch operation.
        async for page in parent.pages():
            params = {}
            for index, resource in enumerate(page):
                # There is no public interface to get a service name
                # or low-level client from a collection, so we get
                # these from the first resource in the collection.
                if service_name is None:
                    service_name = resource.meta.service_name
                if client is None:
                    client = resource.meta.client

                create_request_parameters(
                    resource, self._action_model.request,
                    params=params, index=index)

            if not params:
                # There are no items, no need to make a call.
                break

            params.update(kwargs)

            logger.debug('Calling %s:%s with %r',
                         service_name, operation_name, params)

            response = await (getattr(client, operation_name)(**params))

            logger.debug('Response: %r', response)

            responses.append(
                self._response_handler(parent, params, response))

        return responses


class AIOServiceAction(ServiceAction):
    def __init__(self, action_model, factory=None, service_context=None):
        self._action_model = action_model

        # In the simplest case we just return the response, but if a
        # resource is defined, then we must create these before returning.
        resource_response_model = action_model.resource
        if resource_response_model:
            self._response_handler = AIOResourceHandler(
                search_path=resource_response_model.path,
                factory=factory, resource_model=resource_response_model,
                service_context=service_context,
                operation_name=action_model.request.operation
            ).async_call
        else:
            self._response_handler = AIORawHandler(action_model.path).async_call

    def __call__(self, parent, *args, **kwargs):
        """
        Perform the action's request operation after building operation
        parameters and build any defined resources from the response.

        :type parent: :py:class:`~boto3.resources.base.ServiceResource`
        :param parent: The resource instance to which this action is attached.
        :rtype: dict or ServiceResource or list(ServiceResource)
        :return: The response, either as a raw dict or resource instance(s).
        """
        operation_name = xform_name(self._action_model.request.operation)

        # First, build predefined params and then update with the
        # user-supplied kwargs, which allows overriding the pre-built
        # params if needed.
        params = create_request_parameters(parent, self._action_model.request)
        params.update(kwargs)

        logger.debug('Calling %s:%s with %r', parent.meta.service_name,
                     operation_name, params)

        response = yield from getattr(parent.meta.client, operation_name)(**params)

        logger.debug('Response: %r', response)

        return self._response_handler(parent, params, response)

    async def async_call(self, parent, *args, **kwargs):
        """
        Perform the action's request operation after building operation
        parameters and build any defined resources from the response.

        :type parent: :py:class:`~boto3.resources.base.ServiceResource`
        :param parent: The resource instance to which this action is attached.
        :rtype: dict or ServiceResource or list(ServiceResource)
        :return: The response, either as a raw dict or resource instance(s).
        """
        operation_name = xform_name(self._action_model.request.operation)

        # First, build predefined params and then update with the
        # user-supplied kwargs, which allows overriding the pre-built
        # params if needed.
        params = create_request_parameters(parent, self._action_model.request)
        params.update(kwargs)

        logger.debug('Calling %s:%s with %r', parent.meta.service_name,
                     operation_name, params)

        response = await getattr(parent.meta.client, operation_name)(**params)

        logger.debug('Response: %r', response)

        return await self._response_handler(parent, params, response)


# TODO FIX
class AIOWaiterAction(object):
    """
    A class representing a callable waiter action on a resource, for example
    ``s3.Bucket('foo').wait_until_bucket_exists()``.
    The waiter action may construct parameters from existing resource
    identifiers.

    :type waiter_model: :py:class`~boto3.resources.model.Waiter`
    :param waiter_model: The action waiter.
    :type waiter_resource_name: string
    :param waiter_resource_name: The name of the waiter action for the
                                 resource. It usually begins with a
                                 ``wait_until_``
    """

    def __init__(self, waiter_model, waiter_resource_name):
        self._waiter_model = waiter_model
        self._waiter_resource_name = waiter_resource_name

    def __call__(self, parent, *args, **kwargs):
        """
        Perform the wait operation after building operation
        parameters.

        :type parent: :py:class:`~boto3.resources.base.ServiceResource`
        :param parent: The resource instance to which this action is attached.
        """
        client_waiter_name = xform_name(self._waiter_model.waiter_name)

        # First, build predefined params and then update with the
        # user-supplied kwargs, which allows overriding the pre-built
        # params if needed.
        params = create_request_parameters(parent, self._waiter_model)
        params.update(kwargs)

        logger.debug('Calling %s:%s with %r',
                     parent.meta.service_name,
                     self._waiter_resource_name, params)

        client = parent.meta.client
        waiter = client.get_waiter(client_waiter_name)
        response = waiter.wait(**params)

        logger.debug('Response: %r', response)

    async def async_call(self, parent, *args, **kwargs):
        """
        Perform the wait operation after building operation
        parameters.

        :type parent: :py:class:`~boto3.resources.base.ServiceResource`
        :param parent: The resource instance to which this action is attached.
        """
        client_waiter_name = xform_name(self._waiter_model.waiter_name)

        # First, build predefined params and then update with the
        # user-supplied kwargs, which allows overriding the pre-built
        # params if needed.
        params = create_request_parameters(parent, self._waiter_model)
        params.update(kwargs)

        logger.debug('Calling %s:%s with %r',
                     parent.meta.service_name,
                     self._waiter_resource_name, params)

        client = parent.meta.client
        waiter = client.get_waiter(client_waiter_name)
        response = await waiter.wait(**params)

        logger.debug('Response: %r', response)
