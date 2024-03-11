from aws_cdk import (
    aws_ecs as ecs,
    aws_route53 as route53,
    aws_route53_targets as targets,
    aws_secretsmanager as secretsmanager,
    aws_elasticloadbalancingv2 as elbv2,
    aws_ec2 as ec2,
    aws_iam as iam,
    Stack,
    aws_certificatemanager as acm,
    Duration,
    CfnOutput,
    DefaultStackSynthesizer
)
from random import randrange
from constructs import Construct

class FargateServiceConstruct(Construct):
    def __init__(
        self, 
        scope: Construct, 
        id: str, 
        hosted_zone: route53.IHostedZone, 
        certificate: acm.ICertificate, 
        application: str, 
        environment: str, 
        cpu: int, 
        mem: int, 
        min_capacity: int, 
        max_capacity: int, 
        alb: elbv2.IApplicationLoadBalancer, 
        http_listener: elbv2.ApplicationListener, 
        https_listener: elbv2.ApplicationListener, 
        ecs_security_group: ec2.ISecurityGroup, 
        cluster: ecs.Cluster, 
        account: str, 
        region: str, 
        build_number: int, 
        **kwargs
    ):
        super().__init__(scope, id, **kwargs)
        
        self.application = application
        self.environment = environment
        self.region = region
        self.account = account
        self.cluster = cluster
        self.cpu = cpu
        self.mem = mem
        self.build_number = build_number
        self.alb = alb
        self.http_listener = http_listener
        self.https_listener = https_listener
        self.ecs_security_group = ecs_security_group
        self.hosted_zone = hosted_zone

        self.iam_roles()
        self.loadbalancer_config()
        self.logs()
        self.nginx_container()
        self.app_container()
        self.datadog_container()
        self.service(min_capacity, max_capacity)
        self.route53()

    def iam_roles(self):
        self.task_role = iam.Role(
            self,
            f"{self.application}-{self.environment}-taskRole",
            assumed_by=iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
            description='Role that can be assumed by ECS tasks'
        )
        
        self.execution_role = iam.Role(
            self,
            f"{self.application}-{self.environment}-executionRole",
            assumed_by=iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
            managed_policies=[iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AmazonECSTaskExecutionRolePolicy")]
        )

    def loadbalancer_config(self):
        self.target_group = elbv2.ApplicationTargetGroup(
            self,
            f'{self.application}-TG',
            vpc=self.cluster.vpc,
            protocol=elbv2.ApplicationProtocol.HTTP,
            target_type=elbv2.TargetType.IP
        )
        
        conditions = [elbv2.ListenerCondition.host_headers([f"{self.application}-{self.environment}.{self.hosted_zone.zone_name}"])]
        
        elbv2.ApplicationListenerRule(
            self,
            f'{self.application}-HTTPListenerRule',
            listener=self.http_listener,
            priority=randrange(1, 50000),
            conditions=conditions,
            action=elbv2.ListenerAction.forward([self.target_group])
        )
        
        elbv2.ApplicationListenerRule(
            self,
            f'{self.application}-HTTPSListenerRule',
            listener=self.https_listener,
            priority=randrange(1, 50000),
            conditions=conditions,
            action=elbv2.ListenerAction.forward([self.target_group])
        )

    def logs(self):
        # Assuming Splunk logs configuration function here. 
        # Define according to your specific needs.
        pass

    def nginx_container(self):
        # Define the nginx container based on your specific needs.
        # Example:
        self.task_definition.add_container(
            "nginx",
            image=ecs.ContainerImage.from_asset("path/to/nginx/Dockerfile"),
            logging=ecs.LogDrivers.aws_logs(stream_prefix=f"{self.application}-nginx"),
            cpu=256,
            memory_limit_mib=512,
        )

    def app_container(self):
        # Define the app container including secrets and other configurations.
        # This will vary based on your specific application requirements.
        pass

    def datadog_container(self):
        # Directly use or adapt the existing create_datadog_container function here.
        pass

    def service(self, min_capacity, max_capacity):
        self.fargate_service = ecs.FargateService(
            self,
            f"{self.application}-Service",
            cluster=self.cluster,
            task_definition=self.task_definition,
            security_groups=[self.ecs_security_group],
            desired_count=1,
        )
        
        # Auto Scaling configuration
        scaling = self.fargate_service.auto_scale_task_count(
            min_capacity=min_capacity,
            max_capacity=max_capacity
        )
        
        scaling.scale_on_cpu_utilization(
            "CPUScaling",
            target_utilization_percent=50,
            scale_in_cooldown=Duration.minutes(5),
            scale_out_cooldown=Duration.minutes(5)
        )

    def route53(self):
        route53.ARecord(
            self,
            f"{self.application}-DNS",
            zone=self.hosted_zone,
            target=route53.RecordTarget.from_alias(targets.LoadBalancerTarget(self.alb)),
            record_name=f"{self.application}-{self.environment}-{self.build_number}"
        )
